import logging
from typing import Any

import numpy as np
import pandas as pd

from app.agents.base_agent import BaseAgent
from app.agents.models import ChartAgentResult
from core.models import ChartSpec

logger = logging.getLogger("ForecastAgent")

class ForecastAgent(BaseAgent):
    """Агент Предиктивной Аналитики (Phase 17). 
    Строит прогнозы на базе исторических данных."""
    
    name = "forecast_agent"
    description = "Строит линейный прогноз по историческим данным и возвращает график"
    
    def run(self, question: str, data: list[dict], **kwargs: Any) -> ChartAgentResult:
        if not data:
            return ChartAgentResult(success=False, error="Нет данных для прогноза", reasoning="Пустой датасет", specs=[ChartSpec(chart_type="line", x="period", y="value", title="Ошибка прогноза")])
            
        try:
            df = pd.DataFrame(data)
            
            # Попытаемся найти колонку с датой/периодом
            time_cols = [c for c in df.columns if 'period' in c.lower() or 'date' in c.lower() or 'month' in c.lower()]
            if not time_cols:
                time_cols = [df.columns[0]]
            t_col = time_cols[0]
            
            # Попытаемся найти числовую колонку (значение)
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if not num_cols:
                # Пытаемся конвертнуть вторую колонку
                val_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                df[val_col] = pd.to_numeric(df[val_col], errors='coerce')
            else:
                val_col = num_cols[0]
                
            df = df.dropna(subset=[val_col])
            if df.empty or len(df) < 3:
                # Fallback to normal chart agent
                spec = ChartSpec(chart_type="line", x=t_col, y=val_col, title="Недостаточно исторических данных для прогноза")
                return ChartAgentResult(success=True, reasoning="Мало данных для ML, строим обычный график", specs=[spec])

            # Сортируем по времени
            df = df.sort_values(by=t_col).reset_index(drop=True)
            
            # Простая линейная регрессия
            x = np.arange(len(df))
            y = df[val_col].values
            slope, intercept = np.polyfit(x, y, 1)
            
            # Прогноз на 3 периода вперед
            last_period = str(df[t_col].iloc[-1])
            try:
                # Пытаемся парсить YYYY-MM
                if "-" in last_period:
                    y_str, m_str = last_period.split("-")[:2]
                    curr_y, curr_m = int(y_str), int(m_str)
                    future_periods = []
                    for i in range(1, 4):
                        curr_m += 1
                        if curr_m > 12:
                            curr_m = 1
                            curr_y += 1
                        future_periods.append(f"{curr_y}-{curr_m:02d}")
                else:
                    future_periods = [f"Прогноз {i}" for i in range(1, 4)]
            except Exception:
                future_periods = [f"Прогноз {i}" for i in range(1, 4)]
                
            # Добавляем прогноз в данные (in-place modification)
            for i, fp in enumerate(future_periods):
                future_x = len(df) + i
                pred_y = slope * future_x + intercept
                new_row = {c: None for c in df.columns}
                new_row[t_col] = f"{fp}"
                new_row[val_col] = max(0, pred_y) # не даем уйти ниже нуля
                data.append(new_row)
                
            spec = ChartSpec(
                title=f"Прогноз: {val_col} ({question})",
                chart_type="area",
                x=t_col,
                y=val_col
            )
            
            return ChartAgentResult(
                success=True,
                reasoning=f"Построена линейная регрессия по {len(df)} точкам, добавлен прогноз на 3 периода.",
                specs=[spec]
            )
            
        except Exception as e:
            logger.error(f"Ошибка прогноза: {e}")
            return ChartAgentResult(success=False, error=str(e), reasoning="Ошибка в вычислениях ML", specs=[ChartSpec(chart_type="line", x="period", y="value", title="Ошибка прогноза")])
