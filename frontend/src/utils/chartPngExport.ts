/**
 * Chart PNG card export - renders a styled card with title, chart SVG, and data table.
 * Same off-screen HTML capture strategy as dashboard PDF export.
 */
import html2canvas from 'html2canvas';

const BG_PAGE   = '#0b1123';
const BG_CARD   = '#131c38';
const C_PRIMARY = '#6366f1';
const C_EMERALD = '#34d399';
const C_AMBER   = '#fbbf24';
const C_ROSE    = '#f87171';
const C_WHITE   = '#f1f5f9';
const C_SLATE3  = '#94a3b8';
const C_SLATE5  = '#475569';
const C_BORDER  = '#1e2a4a';

function fmt(val: number): string {
  const abs = Math.abs(val);
  if (abs >= 1e12) return (val / 1e12).toFixed(1).replace(/\.0$/, '') + 'T';
  if (abs >= 1e9)  return (val / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
  if (abs >= 1e6)  return (val / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (abs >= 1e3)  return (val / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return val % 1 === 0 ? String(val) : val.toFixed(1);
}

function buildBarSVG(data: any[], xKey: string, yKey: string, w = 620, h = 200, horizontal = false): string {
  const vals = data.map(d => Number(d[yKey]) || 0);
  const maxVal = Math.max(...vals, 1);
  const n = data.length;
  const PAD_L = horizontal ? 100 : 30;
  const PAD_B = horizontal ? 12 : 32;
  const PAD_T = 20;
  const PAD_R = 60;
  const cW = w - PAD_L - PAD_R;
  const cH = h - PAD_T - PAD_B;
  let bars = '', labels = '';

  const COLORS = [C_PRIMARY, C_EMERALD, C_AMBER, C_ROSE, '#a78bfa', '#22d3ee'];

  if (horizontal) {
    const rowH = cH / n;
    data.forEach((d, i) => {
      const val = vals[i];
      const bw = (val / maxVal) * cW;
      const by = PAD_T + i * rowH + rowH * 0.12;
      const bh = rowH * 0.76;
      const col = COLORS[i % COLORS.length];
      bars += `<rect x="${PAD_L}" y="${by}" width="${bw}" height="${bh}" rx="4" fill="${col}" opacity="0.85"/>`;
      labels += `<text x="${PAD_L - 6}" y="${by + bh / 2 + 4}" text-anchor="end" font-size="11" fill="${C_SLATE3}" font-family="Arial">${String(d[xKey] || '').slice(0, 18)}</text>`;
      labels += `<text x="${PAD_L + bw + 5}" y="${by + bh / 2 + 4}" font-size="10" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${fmt(val)}</text>`;
    });
  } else {
    const colW = cW / n;
    const barW = Math.min(colW * 0.65, 40);
    data.forEach((d, i) => {
      const val = vals[i];
      const bh = (val / maxVal) * cH;
      const bx = PAD_L + i * colW + (colW - barW) / 2;
      const by = PAD_T + cH - bh;
      const col = COLORS[i % COLORS.length];
      bars += `<rect x="${bx}" y="${by}" width="${barW}" height="${bh}" rx="4" fill="${col}" opacity="0.85"/>`;
      labels += `<text x="${bx + barW / 2}" y="${PAD_T + cH + 16}" text-anchor="middle" font-size="10" fill="${C_SLATE3}" font-family="Arial">${String(d[xKey] || '').slice(0, 9)}</text>`;
      labels += `<text x="${bx + barW / 2}" y="${by - 5}" text-anchor="middle" font-size="10" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${fmt(val)}</text>`;
    });
  }

  let grid = '';
  for (let g = 0; g <= 4; g++) {
    if (horizontal) {
      const gx = PAD_L + (g / 4) * cW;
      grid += `<line x1="${gx}" y1="${PAD_T}" x2="${gx}" y2="${PAD_T + cH}" stroke="${C_BORDER}" stroke-width="0.7"/>`;
    } else {
      const gy = PAD_T + (g / 4) * cH;
      grid += `<line x1="${PAD_L}" y1="${gy}" x2="${PAD_L + cW}" y2="${gy}" stroke="${C_BORDER}" stroke-width="0.7"/>`;
    }
  }
  return `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">${grid}${bars}${labels}</svg>`;
}

function buildLineSVG(data: any[], xKey: string, yKey: string, w = 620, h = 200): string {
  if (data.length < 2) return '';
  const vals = data.map(d => Number(d[yKey]) || 0);
  const maxV = Math.max(...vals, 1);
  const minV = Math.min(...vals, 0);
  const range = maxV - minV || 1;
  const PAD = { l: 50, r: 20, t: 20, b: 30 };
  const cW = w - PAD.l - PAD.r;
  const cH = h - PAD.t - PAD.b;
  const n = data.length;
  const pts = data.map((d, i) => ({
    x: PAD.l + (i / (n - 1)) * cW,
    y: PAD.t + cH - ((vals[i] - minV) / range) * cH,
    v: vals[i],
    lbl: String(d[xKey] || '').slice(0, 8),
  }));
  const poly = pts.map(p => `${p.x},${p.y}`).join(' ');
  const area = `${pts[0].x},${PAD.t + cH} ${poly} ${pts[pts.length - 1].x},${PAD.t + cH}`;
  let dots = '', xlabels = '', vlabels = '';
  pts.forEach((p, i) => {
    dots += `<circle cx="${p.x}" cy="${p.y}" r="4" fill="${C_PRIMARY}"/><circle cx="${p.x}" cy="${p.y}" r="2" fill="white"/>`;
    const ly = i % 2 === 0 ? p.y - 9 : p.y + 16;
    vlabels += `<text x="${p.x}" y="${ly}" text-anchor="middle" font-size="10" font-weight="bold" fill="${C_WHITE}" font-family="Arial">${fmt(p.v)}</text>`;
    if (n <= 8 || i === 0 || i === n - 1) {
      xlabels += `<text x="${p.x}" y="${PAD.t + cH + 16}" text-anchor="middle" font-size="10" fill="${C_SLATE3}" font-family="Arial">${p.lbl}</text>`;
    }
  });
  let grid = '';
  for (let g = 0; g <= 3; g++) {
    const gy = PAD.t + (g / 3) * cH;
    const gv = maxV - (g / 3) * range;
    grid += `<line x1="${PAD.l}" y1="${gy}" x2="${PAD.l + cW}" y2="${gy}" stroke="${C_BORDER}" stroke-width="0.7"/>`;
    grid += `<text x="${PAD.l - 4}" y="${gy + 4}" text-anchor="end" font-size="9" fill="${C_SLATE5}" font-family="Arial">${fmt(gv)}</text>`;
  }
  return `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
    ${grid}
    <polygon points="${area}" fill="${C_PRIMARY}" opacity="0.1"/>
    <polyline points="${poly}" fill="none" stroke="${C_PRIMARY}" stroke-width="2.5" stroke-linejoin="round"/>
    ${dots}${vlabels}${xlabels}
  </svg>`;
}

function buildDonutSVG(data: any[], xKey: string, yKey: string, r = 90): string {
  const total = data.reduce((s, d) => s + (Number(d[yKey]) || 0), 0) || 1;
  const COLORS = [C_PRIMARY, C_EMERALD, C_AMBER, C_ROSE, '#a78bfa', '#22d3ee', '#fb923c'];
  const cx = r + 10, cy = r + 10;
  const size = (r + 10) * 2;
  let angle = -Math.PI / 2;
  let paths = '';
  let legend = '';

  data.slice(0, 7).forEach((d, i) => {
    const val = Number(d[yKey]) || 0;
    const slice = (val / total) * Math.PI * 2;
    const ea = angle + slice;
    const ri = r * 0.55;
    const x1 = cx + Math.cos(angle) * r, y1 = cy + Math.sin(angle) * r;
    const x2 = cx + Math.cos(ea) * r,   y2 = cy + Math.sin(ea) * r;
    const xi1 = cx + Math.cos(angle) * ri, yi1 = cy + Math.sin(angle) * ri;
    const xi2 = cx + Math.cos(ea) * ri,   yi2 = cy + Math.sin(ea) * ri;
    const lg = slice > Math.PI ? 1 : 0;
    const col = COLORS[i % COLORS.length];
    paths += `<path d="M${xi1},${yi1} L${x1},${y1} A${r},${r} 0 ${lg},1 ${x2},${y2} L${xi2},${yi2} A${ri},${ri} 0 ${lg},0 ${xi1},${yi1} Z" fill="${col}"/>`;
    const pct = Math.round((val / total) * 100);
    if (pct >= 4) {
      const ma = angle + slice / 2;
      const lx = cx + Math.cos(ma) * (r * 0.77);
      const ly = cy + Math.sin(ma) * (r * 0.77);
      paths += `<text x="${lx}" y="${ly + 4}" text-anchor="middle" font-size="11" fill="white" font-weight="bold" font-family="Arial">${pct}%</text>`;
    }
    const row = Math.floor(i / 2), col2 = i % 2;
    const lx2 = col2 * 160, ly2 = 8 + row * 16;
    legend += `<rect x="${lx2}" y="${ly2}" width="10" height="10" rx="3" fill="${col}"/>`;
    legend += `<text x="${lx2 + 14}" y="${ly2 + 8}" font-size="10" fill="${C_SLATE3}" font-family="Arial">${String(d[xKey] || '').slice(0, 16)} — ${fmt(val)}</text>`;
    angle = ea;
  });

  const legendH = Math.ceil(data.length / 2) * 16 + 12;
  return `<svg width="${size + 20}" height="${size + legendH}" xmlns="http://www.w3.org/2000/svg">
    ${paths}
    <svg y="${size + 4}" x="0" width="${size + 20}" height="${legendH}">${legend}</svg>
  </svg>`;
}

function buildChartSVG(chartObj: any): string {
  const raw: any[] = chartObj.data || [];
  if (!raw.length) return '';
  const type = chartObj.chart_type || 'bar';
  const keys = Object.keys(raw[0]);
  const numKey = keys.find(k => typeof raw[0][k] === 'number') || keys[1] || keys[0];
  const catKey = keys.find(k => typeof raw[0][k] !== 'number') || keys[0];
  const d8 = raw.slice(0, 10);

  switch (type) {
    case 'line':
    case 'area':
      return buildLineSVG(d8, catKey, numKey, 620, 220);
    case 'horizontal_bar':
      return buildBarSVG(d8, catKey, numKey, 620, Math.max(200, d8.length * 28), true);
    case 'pie':
    case 'donut':
      return buildDonutSVG(d8, catKey, numKey, 90);
    default:
      return buildBarSVG(d8, catKey, numKey, 620, 220, false);
  }
}

function buildDataTableHTML(data: any[], maxRows = 8): string {
  if (!data.length) return '';
  const headers = Object.keys(data[0]);
  const rows = data.slice(0, maxRows);
  const headerCells = headers.map(h =>
    `<th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;color:${C_SLATE3};border-bottom:1px solid ${C_BORDER};white-space:nowrap;">${h}</th>`
  ).join('');
  const dataRows = rows.map((row, ri) =>
    `<tr style="background:${ri % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)'}">
      ${headers.map(h => {
        const v = row[h];
        const isNum = typeof v === 'number';
        return `<td style="padding:7px 12px;font-size:11px;color:${isNum ? C_WHITE : C_SLATE3};text-align:${isNum ? 'right' : 'left'};border-bottom:1px solid rgba(30,42,74,0.5);">
          ${isNum ? fmt(v) : String(v ?? '—').slice(0, 30)}
        </td>`;
      }).join('')}
    </tr>`
  ).join('');
  const more = data.length > maxRows ? `<tr><td colspan="${headers.length}" style="padding:6px 12px;font-size:10px;color:${C_SLATE5};text-align:center;">...ещё ${data.length - maxRows} строк</td></tr>` : '';
  return `<table style="width:100%;border-collapse:collapse;">
    <thead><tr>${headerCells}</tr></thead>
    <tbody>${dataRows}${more}</tbody>
  </table>`;
}

export async function exportChartToPNG(chartObj: any, title: string): Promise<void> {
  const chartSVG = buildChartSVG(chartObj);
  const data: any[] = chartObj.data || [];
  const now = new Date().toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });

  const html = `
  <div style="
    width: 700px;
    background: ${BG_PAGE};
    font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
    padding: 0;
    border-radius: 16px;
    overflow: hidden;
  ">
    <!-- Header -->
    <div style="background:${BG_CARD};border-bottom:1px solid ${C_BORDER};padding:20px 28px;display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div style="font-size:9px;color:${C_SLATE5};font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Prototip BI · Analytics</div>
        <div style="font-size:18px;font-weight:800;color:${C_WHITE};line-height:1.2;">${title}</div>
      </div>
      <div style="font-size:10px;color:${C_EMERALD};background:rgba(52,211,153,0.1);border:1px solid rgba(52,211,153,0.2);border-radius:20px;padding:4px 12px;font-weight:600;">● LIVE</div>
    </div>
    <!-- Chart -->
    <div style="padding:24px 28px 16px;background:${BG_PAGE};">
      <div style="background:${BG_CARD};border:1px solid ${C_BORDER};border-radius:12px;padding:20px;overflow:hidden;">
        ${chartSVG || `<div style="color:${C_SLATE5};font-size:13px;text-align:center;padding:40px;">Нет данных для отображения</div>`}
      </div>
    </div>
    <!-- Data Table -->
    ${data.length > 0 ? `
    <div style="padding:0 28px 24px;">
      <div style="font-size:10px;font-weight:700;color:${C_SLATE5};letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">ДАННЫЕ</div>
      <div style="background:${BG_CARD};border:1px solid ${C_BORDER};border-radius:10px;overflow:hidden;">
        ${buildDataTableHTML(data)}
      </div>
    </div>` : ''}
    <!-- Footer -->
    <div style="background:${BG_CARD};border-top:1px solid ${C_BORDER};padding:12px 28px;display:flex;align-items:center;justify-content:space-between;">
      <div style="font-size:10px;color:${C_SLATE5};">Экспортировано: ${now}</div>
      <div style="font-size:10px;color:${C_PRIMARY};">prototip.ai</div>
    </div>
  </div>`;

  const container = document.createElement('div');
  container.style.cssText = `position:fixed;left:-9999px;top:0;z-index:-1;pointer-events:none;`;
  container.innerHTML = html;
  document.body.appendChild(container);

  await new Promise<void>(r => requestAnimationFrame(() => requestAnimationFrame(() => r())));

  try {
    const canvas = await html2canvas(container.firstElementChild as HTMLElement, {
      backgroundColor: BG_PAGE,
      scale: 2,
      useCORS: true,
      logging: false,
      width: 700,
    });

    const link = document.createElement('a');
    link.download = `${title.replace(/\s+/g, '_').slice(0, 50)}.png`;
    link.href = canvas.toDataURL('image/png', 1.0);
    link.click();
  } finally {
    document.body.removeChild(container);
  }
}
