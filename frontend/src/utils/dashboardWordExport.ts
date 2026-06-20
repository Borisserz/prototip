/**
 * Dashboard Word (.docx) Export
 *
 * Собирает Markdown из данных дашборда и отправляет его на серверный эндпоинт
 * POST /api/v1/export/report-docx (Phase 2). Графики передаются как ChartSpec +
 * данные — бэкенд рендерит их через viz/charts и вставляет в .docx. Готовый файл
 * скачивается в браузере.
 */

const API_BASE = 'http://localhost:8000';

/** Безопасное экранирование значения для ячейки Markdown-таблицы. */
function cell(v: any): string {
  if (v == null) return '';
  return String(v).replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

/** Строит Markdown-отчёт и массив графиков для бэкенда. */
function buildPayload(data: any): { markdown: string; title: string; charts: any[] } {
  const title = data.title || 'Аналитический дашборд';
  const summary = data.summary || '';
  const kpiCards: any[] = data.kpi_cards || [];
  const recs: string[] = data.recommendations || [];
  const insights: string[] = data.insights || [];
  const reasoning = data.reasoning || '';
  const rawCharts: any[] = (data.charts || []).filter((c: any) => (c.data || []).length > 0);

  const md: string[] = [];

  if (summary) {
    md.push('## Резюме анализа\n');
    md.push(summary + '\n');
  }

  if (kpiCards.length) {
    md.push('## Ключевые показатели\n');
    md.push('| Метрика | Значение | Ед. | Изменение |');
    md.push('|---|---|---|---|');
    for (const k of kpiCards) {
      const change =
        k.change != null ? `${k.change > 0 ? '▲' : '▼'} ${Math.abs(k.change)}% ${k.change_period || ''}` : '';
      md.push(`| ${cell(k.name)} | ${cell(k.value)} | ${cell(k.unit)} | ${cell(change)} |`);
    }
    md.push('');
  }

  const charts: any[] = [];
  if (rawCharts.length) {
    md.push('## Визуализации\n');
    rawCharts.forEach((c, i) => {
      const placeholder = `chart${i}`;
      const { data: chartData, ...specRest } = c;
      const spec = {
        chart_type: c.chart_type || 'bar',
        title: c.title || `График ${i + 1}`,
        x: c.x || (chartData?.[0] ? Object.keys(chartData[0])[0] : 'x'),
        y: c.y || (chartData?.[0] ? Object.keys(chartData[0])[1] || Object.keys(chartData[0])[0] : 'y'),
        rationale: c.rationale || c.subtitle || '',
        ...specRest,
      };
      delete (spec as any).data;
      charts.push({ placeholder, title: c.title || '', spec, data: chartData });
      md.push(`![${c.title || 'График'}](${placeholder})\n`);
    });
  }

  if (insights.length) {
    md.push('## Ключевые инсайты\n');
    insights.forEach((ins, i) => md.push(`${i + 1}. ${ins}`));
    md.push('');
  }

  if (recs.length) {
    md.push('## Рекомендации ИИ\n');
    recs.forEach((r, i) => md.push(`${i + 1}. ${r}`));
    md.push('');
  }

  if (reasoning) {
    md.push('---\n');
    md.push(`*Методология ИИ: ${reasoning}*`);
  }

  return { markdown: md.join('\n'), title, charts };
}

/** Извлекает имя файла из заголовка Content-Disposition. */
function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  return m ? decodeURIComponent(m[1]) : fallback;
}

export async function exportDashboardToWord(dashboardData: any): Promise<void> {
  const { markdown, title, charts } = buildPayload(dashboardData);

  const resp = await fetch(`${API_BASE}/api/v1/export/report-docx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      markdown,
      title,
      subtitle: 'Сформировано автоматически · Prototip BI',
      charts,
    }),
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Word export failed (${resp.status}): ${text.slice(0, 200)}`);
  }

  const blob = await resp.blob();
  const safe = (title || 'Dashboard')
    .replace(/[^\wа-яёА-ЯЁ\s]/gi, '')
    .trim()
    .replace(/\s+/g, '_')
    .slice(0, 50);
  const filename = filenameFromDisposition(
    resp.headers.get('Content-Disposition'),
    `PrototipBI_${safe}.docx`,
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
