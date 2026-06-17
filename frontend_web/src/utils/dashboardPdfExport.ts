/**
 * Dashboard PDF Export — Clean HTML Capture Strategy
 *
 * Renders a dedicated off-screen export-optimised HTML element,
 * captures it with html2canvas (full height, no clipping),
 * and wraps it in a PDF via jsPDF.
 *
 * Advantages vs. direct DOM capture:
 *  - No overflow/scroll clipping
 *  - No backdrop-blur / glassmorphism that confuses html2canvas
 *  - Solid-color backgrounds that render perfectly
 *  - Correct Cyrillic text (browser renders, canvas captures pixels)
 */

import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';

// ─── Colors ────────────────────────────────────────────────────────────────
const BG_PAGE   = '#0b1123';
const BG_CARD   = '#131c38';
const BG_CARD2  = '#0f1628';
const C_PRIMARY = '#6366f1';
const C_EMERALD = '#34d399';
const C_AMBER   = '#fbbf24';
const C_ROSE    = '#f87171';
const C_WHITE   = '#f1f5f9';
const C_SLATE3  = '#94a3b8';
const C_SLATE5  = '#475569';
const C_BORDER  = '#1e2a4a';

// ─── Inline styles helpers ─────────────────────────────────────────────────
const flex = (gap = 0) => `display:flex;gap:${gap}px;`;
const card = (bg = BG_CARD, border = C_BORDER) =>
  `background:${bg};border:1px solid ${border};border-radius:12px;padding:18px;`;

/** Format large numbers compactly: 13_140_000_000 → 13.1B */
function fmt(val: number): string {
  const abs = Math.abs(val);
  if (abs >= 1e12) return (val / 1e12).toFixed(1).replace(/\.0$/, '') + 'T';
  if (abs >= 1e9)  return (val / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
  if (abs >= 1e6)  return (val / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (abs >= 1e3)  return (val / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return val % 1 === 0 ? String(val) : val.toFixed(1);
}

// ─── Build chart mini-SVG (bar) ─────────────────────────────────────────────
function buildBarSVG(
  rawData: any[],
  xKey: string,
  yKey: string,
  w = 380, h = 160,
  color = C_PRIMARY,
  horizontal = false
): string {
  if (!rawData.length) return '';
  const values = rawData.map(d => Number(d[yKey]) || 0);
  const maxVal = Math.max(...values, 1);
  const PAD_L = horizontal ? 80 : 20;
  const PAD_B = horizontal ? 10 : 28;
  const PAD_T = 10;
  const PAD_R = 10;
  const cW = w - PAD_L - PAD_R;
  const cH = h - PAD_T - PAD_B;
  const n = rawData.length;

  let bars = '';
  let labels = '';

  if (horizontal) {
    const rowH = cH / n;
    rawData.forEach((d, i) => {
      const val = Number(d[yKey]) || 0;
      const bw = (val / maxVal) * cW;
      const by = PAD_T + i * rowH + rowH * 0.15;
      const bh = rowH * 0.7;
      bars += `<rect x="${PAD_L}" y="${by}" width="${bw}" height="${bh}" rx="3" fill="${color}" opacity="0.85"/>`;
      const label = String(d[xKey] || '').slice(0, 16);
      labels += `<text x="${PAD_L - 4}" y="${by + bh / 2 + 4}" text-anchor="end" font-size="9" fill="${C_SLATE3}" font-family="Arial">${label}</text>`;
      // value label at end of bar
      const valLabel = fmt(val);
      labels += `<text x="${PAD_L + bw + 3}" y="${by + bh / 2 + 4}" text-anchor="start" font-size="8.5" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${valLabel}</text>`;
    });
  } else {
    const colW = cW / n;
    const barW = Math.min(colW * 0.6, 28);
    rawData.forEach((d, i) => {
      const val = Number(d[yKey]) || 0;
      const bh = (val / maxVal) * cH;
      const bx = PAD_L + i * colW + (colW - barW) / 2;
      const by = PAD_T + cH - bh;
      bars += `<rect x="${bx}" y="${by}" width="${barW}" height="${bh}" rx="3" fill="${color}" opacity="0.85"/>`;
      const label = String(d[xKey] || '').slice(0, 8);
      labels += `<text x="${bx + barW / 2}" y="${PAD_T + cH + 14}" text-anchor="middle" font-size="8" fill="${C_SLATE3}" font-family="Arial">${label}</text>`;
      // value label above bar
      const valLabel = fmt(val);
      labels += `<text x="${bx + barW / 2}" y="${by - 3}" text-anchor="middle" font-size="8" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${valLabel}</text>`;
    });
  }

  // Gridlines
  let grid = '';
  for (let g = 0; g <= 4; g++) {
    if (horizontal) {
      const gx = PAD_L + (g / 4) * cW;
      grid += `<line x1="${gx}" y1="${PAD_T}" x2="${gx}" y2="${PAD_T + cH}" stroke="${C_BORDER}" stroke-width="0.5"/>`;
    } else {
      const gy = PAD_T + (g / 4) * cH;
      grid += `<line x1="${PAD_L}" y1="${gy}" x2="${PAD_L + cW}" y2="${gy}" stroke="${C_BORDER}" stroke-width="0.5"/>`;
    }
  }

  return `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">${grid}${bars}${labels}</svg>`;
}

function buildLineSVG(rawData: any[], xKey: string, yKey: string, w = 380, h = 160): string {
  if (rawData.length < 2) return '';
  const vals = rawData.map(d => Number(d[yKey]) || 0);
  const maxV = Math.max(...vals, 1);
  const minV = Math.min(...vals, 0);
  const range = maxV - minV || 1;
  const PAD = { l: 30, r: 12, t: 12, b: 24 };
  const cW = w - PAD.l - PAD.r;
  const cH = h - PAD.t - PAD.b;
  const n = rawData.length;

  const pts = rawData.map((d, i) => ({
    x: PAD.l + (i / (n - 1)) * cW,
    y: PAD.t + cH - ((Number(d[yKey]) || 0 - minV) / range) * cH,
  }));

  const polyline = pts.map(p => `${p.x},${p.y}`).join(' ');
  const area = `${PAD.l},${PAD.t + cH} ${polyline} ${PAD.l + cW},${PAD.t + cH}`;

  let dots = '';
  let xlabels = '';
  let valLabels = '';
  pts.forEach((p, i) => {
    dots += `<circle cx="${p.x}" cy="${p.y}" r="3" fill="${C_PRIMARY}"/><circle cx="${p.x}" cy="${p.y}" r="1.5" fill="white"/>`;
    const valLabel = fmt(Number(rawData[i][yKey]) || 0);
    // Value above dot (alternate above/below to avoid overlap)
    const labelY = i % 2 === 0 ? p.y - 7 : p.y + 14;
    valLabels += `<text x="${p.x}" y="${labelY}" text-anchor="middle" font-size="8" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${valLabel}</text>`;
    if (i === 0 || i === n - 1 || n <= 6) {
      const lbl = String(rawData[i][xKey] || '').slice(0, 8);
      xlabels += `<text x="${p.x}" y="${PAD.t + cH + 14}" text-anchor="middle" font-size="8" fill="${C_SLATE3}" font-family="Arial">${lbl}</text>`;
    }
  });

  let grid = '';
  for (let g = 0; g <= 3; g++) {
    const gy = PAD.t + (g / 3) * cH;
    grid += `<line x1="${PAD.l}" y1="${gy}" x2="${PAD.l + cW}" y2="${gy}" stroke="${C_BORDER}" stroke-width="0.5"/>`;
  }

  return `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
    ${grid}
    <polygon points="${area}" fill="${C_PRIMARY}" opacity="0.12"/>
    <polyline points="${polyline}" fill="none" stroke="${C_PRIMARY}" stroke-width="2" stroke-linejoin="round"/>
    ${dots}${xlabels}${valLabels}
  </svg>`;
}

function buildDonutSVG(rawData: any[], xKey: string, yKey: string, r = 70): string {
  if (!rawData.length) return '';
  const total = rawData.reduce((s, d) => s + (Number(d[yKey]) || 0), 0) || 1;
  const COLORS = [C_PRIMARY, C_EMERALD, C_AMBER, C_ROSE, '#a78bfa', '#22d3ee', '#fb923c'];
  const cx = r + 10;
  const cy = r + 10;
  const size = (r + 10) * 2;
  let angle = -Math.PI / 2;
  let paths = '';
  let legend = '';

  rawData.slice(0, 7).forEach((d, i) => {
    const slice = ((Number(d[yKey]) || 0) / total) * Math.PI * 2;
    const ea = angle + slice;
    const x1 = cx + Math.cos(angle) * r, y1 = cy + Math.sin(angle) * r;
    const x2 = cx + Math.cos(ea) * r,    y2 = cy + Math.sin(ea) * r;
    const ri = r * 0.55;
    const xi1 = cx + Math.cos(angle) * ri, yi1 = cy + Math.sin(angle) * ri;
    const xi2 = cx + Math.cos(ea) * ri,    yi2 = cy + Math.sin(ea) * ri;
    const lg = slice > Math.PI ? 1 : 0;
    const col = COLORS[i % COLORS.length];
    paths += `<path d="M${xi1},${yi1} L${x1},${y1} A${r},${r} 0 ${lg},1 ${x2},${y2} L${xi2},${yi2} A${ri},${ri} 0 ${lg},0 ${xi1},${yi1} Z" fill="${col}"/>`;
    const pct = Math.round(((Number(d[yKey]) || 0) / total) * 100);
    if (pct >= 5) {
      const ma = angle + slice / 2;
      const lx = cx + Math.cos(ma) * (r * 0.77);
      const ly = cy + Math.sin(ma) * (r * 0.77);
      paths += `<text x="${lx}" y="${ly+3}" text-anchor="middle" font-size="9" fill="white" font-weight="bold" font-family="Arial">${pct}%</text>`;
    }
    const ly2 = 8 + Math.floor(i / 3) * 14;
    const lx2 = (i % 3) * 70;
    legend += `<rect x="${lx2}" y="${ly2}" width="8" height="8" rx="2" fill="${col}"/>
               <text x="${lx2 + 11}" y="${ly2 + 7}" font-size="8" fill="${C_SLATE3}" font-family="Arial">${String(d[xKey] || '').slice(0, 10)}</text>`;
    angle = ea;
  });

  const legendH = Math.ceil(rawData.length / 3) * 14 + 8;
  return `<svg width="${size + 20}" height="${size + legendH}" xmlns="http://www.w3.org/2000/svg">
    ${paths}
    <svg y="${size + 2}" x="0" width="${size + 20}" height="${legendH}">${legend}</svg>
  </svg>`;
}

// ─── Chart renderer ─────────────────────────────────────────────────────────
function buildChartSVG(chartObj: any, w = 380): string {
  const raw: any[] = chartObj.data || [];
  if (!raw.length) return '<span style="color:#475569;font-size:12px">Нет данных</span>';
  const type = chartObj.chart_type || 'bar';
  const keys = Object.keys(raw[0]);
  const numKey = keys.find(k => typeof raw[0][k] === 'number') || keys[1] || keys[0];
  const catKey = keys.find(k => typeof raw[0][k] !== 'number') || keys[0];
  const data8 = raw.slice(0, 8);

  switch (type) {
    case 'line':
    case 'area':
      return buildLineSVG(data8, catKey, numKey, w, 160);
    case 'horizontal_bar':
      return buildBarSVG(data8, catKey, numKey, w, Math.max(160, data8.length * 22), C_PRIMARY, true);
    case 'pie':
    case 'donut':
      return buildDonutSVG(data8, catKey, numKey, 70);
    default:
      return buildBarSVG(data8, catKey, numKey, w, 160, C_PRIMARY, false);
  }
}

// ─── Build full HTML ─────────────────────────────────────────────────────────
function buildExportHTML(data: any): string {
  const title       = data.title        || 'Дашборд';
  const summary     = data.summary      || '';
  const kpiCards    = data.kpi_cards    || [];
  const recs        = data.recommendations || [];
  const insights    = data.insights     || [];
  const charts      = (data.charts || []).filter((c: any) => (c.data || []).length > 0);
  const reasoning   = data.reasoning   || '';
  const now = new Date().toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });

  // ── Header ──────────────────────────────────────────────────────────────
  const headerHTML = `
    <div style="background:${BG_CARD2};border-bottom:1px solid ${C_BORDER};padding:24px 40px;${flex(16)}align-items:center;">
      <div style="background:#1e2a4a;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:700;color:${C_PRIMARY};">
        Prototip <span style="color:${C_SLATE3};font-weight:400;">BI</span>
      </div>
      <div style="flex:1;padding-left:16px;">
        <div style="font-size:20px;font-weight:800;color:${C_WHITE};line-height:1.2;">${title}</div>
        <div style="font-size:11px;color:${C_SLATE3};margin-top:4px;">AI-сгенерированный аналитический дашборд · ${now}</div>
      </div>
      <div style="font-size:11px;color:${C_SLATE5};text-align:right;">
        <div style="display:inline-block;background:#1e2a4a;border-radius:20px;padding:4px 12px;color:${C_EMERALD};font-weight:600;font-size:10px;">
          ● LIVE ANALYTICS
        </div>
      </div>
    </div>`;

  // ── Summary ─────────────────────────────────────────────────────────────
  const summaryHTML = summary ? `
    <div style="${card('#0f1d36', C_PRIMARY)}border-left:4px solid ${C_PRIMARY};">
      <div style="font-size:12px;font-weight:700;color:${C_WHITE};margin-bottom:8px;">ℹ Резюме анализа</div>
      <div style="font-size:12px;color:${C_SLATE3};line-height:1.6;">${summary}</div>
    </div>` : '';

  // ── KPIs ────────────────────────────────────────────────────────────────
  const kpiHTML = kpiCards.length ? `
    <div>
      <div style="font-size:10px;font-weight:700;color:${C_SLATE5};letter-spacing:1px;margin-bottom:12px;text-transform:uppercase;">Ключевые показатели</div>
      <div style="${flex(12)}flex-wrap:wrap;">
        ${kpiCards.slice(0, 4).map((k: any) => `
          <div style="${card()}flex:1;min-width:160px;">
            <div style="font-size:11px;color:${C_SLATE3};margin-bottom:8px;line-height:1.3;">${k.name || ''}</div>
            <div style="${flex(6)}align-items:baseline;">
              <span style="font-size:24px;font-weight:800;color:${C_WHITE};">${k.value ?? '—'}</span>
              ${k.unit ? `<span style="font-size:11px;color:${C_SLATE5};margin-left:4px;">${k.unit}</span>` : ''}
            </div>
            ${k.change != null ? `
              <div style="font-size:10px;color:${k.change > 0 ? C_EMERALD : C_ROSE};margin-top:6px;">
                ${k.change > 0 ? '▲' : '▼'} ${Math.abs(k.change)}% ${k.change_period || ''}
              </div>` : ''}
          </div>`).join('')}
      </div>
    </div>` : '';

  // ── Recommendations ─────────────────────────────────────────────────────
  const recHTML = recs.length ? `
    <div>
      <div style="font-size:10px;font-weight:700;color:${C_EMERALD};letter-spacing:1px;margin-bottom:12px;text-transform:uppercase;">Рекомендации ИИ</div>
      <div style="${flex(12)}flex-wrap:wrap;">
        ${recs.slice(0, 3).map((r: string, i: number) => `
          <div style="${card('#0d2018', '#1a4a30')}flex:1;min-width:180px;border-left:4px solid ${C_EMERALD};">
            <div style="width:26px;height:26px;border-radius:50%;background:${C_EMERALD};color:#0d2018;line-height:26px;text-align:center;font-weight:800;font-size:12px;margin-bottom:8px;">${i + 1}</div>
            <div style="font-size:11px;color:${C_SLATE3};line-height:1.55;">${r}</div>
          </div>`).join('')}
      </div>
    </div>` : '';

  // ── Charts ───────────────────────────────────────────────────────────────
  const chartHTML = charts.length ? `
    <div>
      <div style="font-size:10px;font-weight:700;color:${C_SLATE5};letter-spacing:1px;margin-bottom:12px;text-transform:uppercase;">Визуализации</div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;">
        ${charts.map((c: any) => `
          <div style="${card()}grid-column:${charts.length === 1 ? 'span 2' : 'span 1'};">
            <div style="font-size:12px;font-weight:700;color:${C_WHITE};margin-bottom:10px;">${c.title || ''}</div>
            <div style="overflow:hidden;">${buildChartSVG(c, 340)}</div>
          </div>`).join('')}
      </div>
    </div>` : '';

  // ── Insights ─────────────────────────────────────────────────────────────
  const insightHTML = insights.length ? `
    <div>
      <div style="font-size:10px;font-weight:700;color:${C_AMBER};letter-spacing:1px;margin-bottom:12px;text-transform:uppercase;">Ключевые инсайты</div>
      <div style="${flex(10)}flex-direction:column;">
        ${insights.map((ins: string, i: number) => `
          <div style="${card()}${flex(12)}align-items:flex-start;">
            <div style="width:26px;height:26px;min-width:26px;border-radius:50%;background:${C_AMBER};color:#1a0a00;line-height:26px;text-align:center;font-weight:800;font-size:12px;flex-shrink:0;">${i + 1}</div>
            <div style="font-size:12px;color:${C_SLATE3};line-height:1.6;">${ins}</div>
          </div>`).join('')}
      </div>
    </div>` : '';

  // ── Reasoning ────────────────────────────────────────────────────────────
  const reasonHTML = reasoning ? `
    <div style="border-top:1px solid ${C_BORDER};padding-top:16px;${flex(12)}align-items:flex-start;">
      <div style="font-size:10px;font-weight:700;color:${C_SLATE5};letter-spacing:1px;text-transform:uppercase;white-space:nowrap;">Методология ИИ</div>
      <div style="font-size:10px;color:${C_SLATE5};line-height:1.5;">${reasoning}</div>
    </div>` : '';

  // ── Footer ────────────────────────────────────────────────────────────────
  const footerHTML = `
    <div style="background:${BG_CARD2};border-top:1px solid ${C_BORDER};padding:14px 40px;${flex(0)}align-items:center;justify-content:space-between;">
      <div style="font-size:10px;color:${C_SLATE5};">Prototip BI — Analytics Dashboard Export · ${now}</div>
      <div style="font-size:10px;color:${C_PRIMARY};">prototip.ai</div>
    </div>`;

  return `
    <div style="
      width: 900px;
      background: ${BG_PAGE};
      font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
      color: ${C_WHITE};
    ">
      ${headerHTML}
      <div style="padding: 32px 40px; display:flex; flex-direction:column; gap:28px;">
        ${summaryHTML}
        ${kpiHTML}
        ${recHTML}
        ${chartHTML}
        ${insightHTML}
        ${reasonHTML}
      </div>
      ${footerHTML}
    </div>`;
}

// ─── Main ────────────────────────────────────────────────────────────────────
export async function exportDashboardToPDF(dashboardData: any): Promise<void> {
  // 1. Build off-screen container
  const container = document.createElement('div');
  container.style.cssText = `
    position: fixed;
    left: -9999px;
    top: 0;
    z-index: -1;
    pointer-events: none;
  `;
  container.innerHTML = buildExportHTML(dashboardData);
  document.body.appendChild(container);

  // 2. Wait for browser to layout
  await new Promise<void>(r => requestAnimationFrame(() => requestAnimationFrame(() => r())));

  try {
    // 3. Capture with html2canvas at 2x resolution
    const canvas = await html2canvas(container.firstElementChild as HTMLElement, {
      backgroundColor: BG_PAGE,
      scale: 2,
      useCORS: true,
      logging: false,
      width: 900,
    });

    // 4. Build PDF sized to canvas aspect ratio (A4-width base)
    const PDF_W = 210; // mm A4 width
    const pxW = canvas.width;
    const pxH = canvas.height;
    const PDF_H = (pxH / pxW) * PDF_W;

    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: [PDF_W, PDF_H],
    });

    pdf.addImage(
      canvas.toDataURL('image/png', 1.0),
      'PNG',
      0, 0,
      PDF_W, PDF_H,
      undefined,
      'FAST'
    );

    const filename = `PrototipBI_${(dashboardData.title || 'Dashboard')
      .replace(/[^\wа-яёА-ЯЁ\s]/gi, '')
      .trim()
      .replace(/\s+/g, '_')
      .slice(0, 50)}.pdf`;

    pdf.save(filename);
  } finally {
    document.body.removeChild(container);
  }
}
