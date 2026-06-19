/**
 * Forecast API client (Phase 3 — предиктивная аналитика).
 *
 * Отправляет временной ряд дашборда на серверный эндпоинт POST /api/v1/forecast.
 * Бэкенд прогоняет ForecastAnalystAgent (numpy/scipy/опц. statsmodels) и
 * возвращает числовой прогноз, доверительные интервалы, метрики и нарратив.
 */

const API_BASE = 'http://localhost:8000';

export interface ForecastPoint {
  period: string;
  value: number;
  lower: number;
  upper: number;
}

export interface ForecastResponse {
  success: boolean;
  narrative: string;
  method: string;
  horizon: number;
  forecast: ForecastPoint[];
  metrics: Record<string, any>;
  /** История + прогноз. Ключи x/y — это поля .x и .y ответа; на прогнозных строках есть lower/upper и is_forecast=true. */
  data: Array<Record<string, any>>;
  x: string;
  y: string;
  title: string;
  reasoning?: string;
}

/** Строит прогноз по строкам временного ряда (история). */
export async function requestForecast(
  rows: Array<Record<string, any>>,
  question = 'Построй прогноз по историческим данным дашборда.',
  horizon = 6,
): Promise<ForecastResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/forecast`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: rows, question, horizon }),
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    let detail = text.slice(0, 300);
    try {
      const j = JSON.parse(text);
      detail = j.detail || detail;
    } catch {
      /* keep raw text */
    }
    throw new Error(`Прогноз не построен (${resp.status}): ${detail}`);
  }

  return resp.json();
}
