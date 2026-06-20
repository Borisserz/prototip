# Frontend — React + Vite + Tailwind

Веб-интерфейс платформы: чат с AI-аналитиком, дашборды, презентации, экспорт и
**админ-консоль клиентов (Phase 6)** — «Мои блоки», статистика по каждому клиенту,
создание новых клиентов и вход «от лица заказчика».

## Стек
React 19 · TypeScript · Vite · TailwindCSS · Zustand · Recharts · Framer Motion · lucide-react

## Структура
```
src/
├── components/
│   ├── admin/        # админ-консоль клиентов (Phase 6)
│   ├── chat/         # чат, графики, виджеты
│   ├── dashboard/    # AI-дашборды, инсайты, прогноз
│   ├── presentation/ # генерация и просмотр презентаций
│   ├── pdf/          # экспорт PDF
│   ├── layout/       # шапка, модалки
│   └── ui/           # базовый UI-кит (button, card, input)
├── lib/              # API-клиент админки, утилиты, JWT-хелперы
├── store/            # Zustand store
├── hooks/            # WebSocket чата
└── utils/            # форматтеры, экспортёры
```

## Запуск

### В Docker
Из корневого `docker-compose.yml`:
```bash
docker compose up -d --build frontend     # → http://localhost:3000
```

### Локально
```bash
npm install
npm run dev        # → http://localhost:5173 (проксирует API на http://localhost:8000)
npm run build      # production-сборка в dist/
npm run lint
```

> API-базовый URL — `http://localhost:8000` (см. `src/lib/adminApi.ts`).
