/**
 * Единая точка конфигурации фронтенда.
 *
 * Базовый URL бэкенда берётся из переменной окружения Vite `VITE_API_BASE`
 * (см. frontend/.env.example). Локальный fallback оставлен для удобства
 * разработки. Не хардкодьте `http://localhost:8000` по компонентам —
 * импортируйте `API_BASE` отсюда.
 */
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";
