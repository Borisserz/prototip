"""Движок прогнозирования (предиктивная аналитика).

Чистые числовые функции экстраполяции временных рядов на базе numpy/scipy
(+ опционально statsmodels для Holt-Winters). Никаких зависимостей от LLM и
проекта — модуль самодостаточен и легко тестируется/переиспользуется в scripts/.

Контракт: на вход подаётся числовой ряд (и опционально метки периодов), на выход
— структура с прогнозом, доверительными интервалами и метриками (числа). Текстовое
описание делает уже LLM-агент (ForecastAnalystAgent), а не Модуль.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

try:  # statsmodels опционален
    from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

    _HAS_SM = True
except Exception:  # pragma: no cover
    _HAS_SM = False

Z_95 = 1.959963984540054  # квантиль нормального распределения для 95% ДИ


@dataclass
class ForecastPoint:
    label: str
    value: float
    lower: float
    upper: float


@dataclass
class ForecastResult:
    method: str
    horizon: int
    history_labels: list[str]
    history_values: list[float]
    forecast: list[ForecastPoint]
    metrics: dict[str, Any] = field(default_factory=dict)
    seasonal: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def combined_rows(self, label_key: str = "period", value_key: str = "value") -> list[dict]:
        """История + прогноз в виде строк для графика (с флагом is_forecast)."""
        rows: list[dict] = []
        for lbl, val in zip(self.history_labels, self.history_values, strict=False):
            rows.append({label_key: lbl, value_key: round(float(val), 4), "is_forecast": False})
        for p in self.forecast:
            rows.append(
                {
                    label_key: p.label,
                    value_key: round(float(p.value), 4),
                    "lower": round(float(p.lower), 4),
                    "upper": round(float(p.upper), 4),
                    "is_forecast": True,
                }
            )
        return rows


# ─── вспомогательные: метки периодов ─────────────────────────────────────────
_MONTH_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})$")
_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_YEAR_RE = re.compile(r"^(\d{4})$")
_QUARTER_RE = re.compile(r"^(\d{4})[-\s]?[QКк]([1-4])$", re.IGNORECASE)


def next_labels(last_label: str, horizon: int) -> list[str]:
    """Генерирует метки будущих периодов, продолжая формат последней метки."""
    s = str(last_label).strip()

    m = _MONTH_RE.match(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        out = []
        for _ in range(horizon):
            mo += 1
            if mo > 12:
                mo = 1
                y += 1
            out.append(f"{y}-{mo:02d}")
        return out

    m = _QUARTER_RE.match(s)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        out = []
        for _ in range(horizon):
            q += 1
            if q > 4:
                q = 1
                y += 1
            out.append(f"{y}-Q{q}")
        return out

    m = _DATE_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            from datetime import timedelta

            base = date(y, mo, d)
            return [(base + timedelta(days=30 * (i + 1))).isoformat() for i in range(horizon)]
        except Exception:
            pass

    m = _YEAR_RE.match(s)
    if m:
        y = int(m.group(1))
        return [str(y + i + 1) for i in range(horizon)]

    return [f"Прогноз {i + 1}" for i in range(horizon)]


def _detect_seasonal_periods(n: int) -> int | None:
    """Грубая эвристика периода сезонности по длине ряда."""
    if n >= 24:
        return 12  # месячные данные, годовая сезонность
    if n >= 8:
        return 4  # квартальные
    return None


# ─── основные методы ──────────────────────────────────────────────────────────
def _linear(y: np.ndarray, horizon: int) -> tuple[np.ndarray, float, float, float]:
    """Линейная регрессия (МНК). Возвращает (прогноз, slope, intercept, r2)."""
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-9
    r2 = 1.0 - ss_res / ss_tot
    fx = np.arange(len(y), len(y) + horizon, dtype=float)
    pred = slope * fx + intercept
    return pred, float(slope), float(intercept), float(r2)


def _resid_std(y: np.ndarray) -> float:
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    return float(np.std(resid, ddof=1)) if len(y) > 2 else float(np.std(resid))


def forecast_series(
    values: list[float],
    horizon: int = 3,
    labels: list[str] | None = None,
    method: str = "auto",
    non_negative: bool = True,
) -> ForecastResult:
    """Главная точка входа: прогноз числового ряда на `horizon` периодов вперёд.

    method: 'auto' | 'linear' | 'holt_winters' | 'mean'
    """
    y = np.array([float(v) for v in values if v is not None], dtype=float)
    warnings: list[str] = []
    n = len(y)

    hist_labels = [str(x) for x in (labels or list(range(n)))][:n]
    if len(hist_labels) < n:
        hist_labels += [str(i) for i in range(len(hist_labels), n)]

    last_label = hist_labels[-1] if hist_labels else "0"
    fut_labels = next_labels(last_label, horizon)

    if n < 2:
        warnings.append("Недостаточно точек для прогноза — возвращаю константу.")
        const = float(y[-1]) if n else 0.0
        pts = [ForecastPoint(fl, const, const, const) for fl in fut_labels]
        return ForecastResult(
            "constant", horizon, hist_labels, y.tolist(), pts, {}, False, warnings
        )

    seasonal_periods = _detect_seasonal_periods(n)
    chosen = method
    if method == "auto":
        if _HAS_SM and seasonal_periods and n >= 2 * seasonal_periods:
            chosen = "holt_winters"
        else:
            chosen = "linear"

    resid_std = _resid_std(y)
    pred: np.ndarray
    metrics: dict[str, Any] = {}
    seasonal = False

    if chosen == "holt_winters" and _HAS_SM:
        try:
            model = ExponentialSmoothing(
                y, trend="add", seasonal="add", seasonal_periods=seasonal_periods
            ).fit()
            pred = np.asarray(model.forecast(horizon), dtype=float)
            seasonal = True
            metrics["sse"] = float(getattr(model, "sse", float("nan")))
            metrics["seasonal_periods"] = seasonal_periods
            resid = y - np.asarray(model.fittedvalues, dtype=float)
            resid_std = float(np.std(resid, ddof=1)) if n > 2 else float(np.std(resid))
        except Exception as e:  # graceful fallback
            warnings.append(f"Holt-Winters недоступен ({e}), использую линейный тренд.")
            chosen = "linear"

    if chosen == "linear":
        pred, slope, intercept, r2 = _linear(y, horizon)
        metrics.update({"slope": slope, "intercept": intercept, "r2": r2})
    elif chosen == "mean":
        m = float(y.mean())
        pred = np.full(horizon, m, dtype=float)
        metrics["mean"] = m

    # доверительный интервал (расширяется с горизонтом)
    pts: list[ForecastPoint] = []
    for h, val in enumerate(pred, start=1):
        margin = Z_95 * resid_std * math.sqrt(1.0 + h / max(n, 1))
        lo = val - margin
        hi = val + margin
        if non_negative and float(np.min(y)) >= 0:
            lo = max(0.0, lo)
            val = max(0.0, val)
        pts.append(ForecastPoint(fut_labels[h - 1], float(val), float(lo), float(hi)))

    # общие метрики динамики
    base = float(y[-1]) or 1e-9
    last_pred = pts[-1].value if pts else base
    metrics["last_value"] = float(y[-1])
    metrics["forecast_last"] = float(last_pred)
    metrics["growth_abs"] = float(last_pred - y[-1])
    metrics["growth_pct"] = float((last_pred - y[-1]) / abs(base) * 100.0)
    metrics["mean_history"] = float(y.mean())

    return ForecastResult(
        method=chosen,
        horizon=horizon,
        history_labels=hist_labels,
        history_values=y.tolist(),
        forecast=pts,
        metrics=metrics,
        seasonal=seasonal,
        warnings=warnings,
    )


def detect_time_value_columns(rows: list[dict]) -> tuple[str | None, str | None]:
    """Эвристически определяет колонку периода и числовую колонку значения."""
    if not rows:
        return None, None
    cols = list(rows[0].keys())
    time_kw = (
        "period",
        "date",
        "month",
        "year",
        "quarter",
        "день",
        "дата",
        "месяц",
        "год",
        "период",
    )
    time_col = next((c for c in cols if any(k in c.lower() for k in time_kw)), None)

    def is_num(col: str) -> bool:
        cnt = 0
        for r in rows[:20]:
            v = r.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cnt += 1
            elif isinstance(v, str):
                try:
                    float(v.replace(" ", "").replace(",", "."))
                    cnt += 1
                except Exception:
                    pass
        return cnt >= max(1, len(rows[:20]) // 2)

    num_cols = [c for c in cols if c != time_col and is_num(c)]
    value_col = num_cols[0] if num_cols else (cols[1] if len(cols) > 1 else cols[0])
    if time_col is None:
        time_col = cols[0]
    return time_col, value_col
