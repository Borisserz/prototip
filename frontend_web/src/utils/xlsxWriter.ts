/**
 * Minimal pure-JS XLSX writer
 * Generates a real .xlsx file (OpenXML format) with no external dependencies.
 * Supports: string cells, number cells, header row styling.
 */

function escapeXml(str: string): string {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function colName(idx: number): string {
  let name = '';
  idx += 1;
  while (idx > 0) {
    const rem = (idx - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    idx = Math.floor((idx - 1) / 26);
  }
  return name;
}

function buildXlsx(data: any[]): Uint8Array {
  if (!data || !data.length) data = [{}];

  const headers = Object.keys(data[0]);

  // Build shared strings (for string cells)
  const sharedStrings: string[] = [];
  const ssMap = new Map<string, number>();

  function ss(val: string): number {
    if (!ssMap.has(val)) {
      ssMap.set(val, sharedStrings.length);
      sharedStrings.push(val);
    }
    return ssMap.get(val)!;
  }

  // Pre-register headers
  headers.forEach(h => ss(h));

  // Build row XML
  let sheetRows = '';

  // Header row
  let headerCells = '';
  headers.forEach((h, ci) => {
    headerCells += `<c r="${colName(ci)}1" t="s" s="1"><v>${ss(h)}</v></c>`;
  });
  sheetRows += `<row r="1">${headerCells}</row>`;

  // Data rows
  data.forEach((row, ri) => {
    let cells = '';
    headers.forEach((h, ci) => {
      const val = row[h];
      const cellRef = `${colName(ci)}${ri + 2}`;
      if (val === null || val === undefined) {
        cells += `<c r="${cellRef}"><v></v></c>`;
      } else if (typeof val === 'number') {
        cells += `<c r="${cellRef}"><v>${val}</v></c>`;
      } else {
        cells += `<c r="${cellRef}" t="s"><v>${ss(String(val))}</v></c>`;
      }
    });
    sheetRows += `<row r="${ri + 2}">${cells}</row>`;
  });

  const sharedStringsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${sharedStrings.length}" uniqueCount="${sharedStrings.length}">
${sharedStrings.map(s => `<si><t>${escapeXml(s)}</t></si>`).join('')}
</sst>`;

  const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>${sheetRows}</sheetData>
</worksheet>`;

  const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts><font><b/><name val="Calibri"/><sz val="11"/></font><font><name val="Calibri"/><sz val="11"/></font></fonts>
<fills><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs>
  <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/>
  <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
</cellXfs>
</styleSheet>`;

  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
</workbook>`;

  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;

  const relsRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`;

  // Build ZIP (minimal PKZIP)
  const files: Array<{ name: string; data: Uint8Array }> = [
    { name: '[Content_Types].xml',      data: strToUint8(contentTypes) },
    { name: '_rels/.rels',              data: strToUint8(relsRels) },
    { name: 'xl/workbook.xml',          data: strToUint8(workbookXml) },
    { name: 'xl/_rels/workbook.xml.rels', data: strToUint8(workbookRels) },
    { name: 'xl/worksheets/sheet1.xml', data: strToUint8(sheetXml) },
    { name: 'xl/sharedStrings.xml',     data: strToUint8(sharedStringsXml) },
    { name: 'xl/styles.xml',            data: strToUint8(stylesXml) },
  ];

  return buildZip(files);
}

function strToUint8(str: string): Uint8Array {
  const buf = new TextEncoder().encode(str);
  return buf;
}

// Minimal uncompressed ZIP builder
function buildZip(files: Array<{ name: string; data: Uint8Array }>): Uint8Array {
  const parts: Uint8Array[] = [];
  const centralDir: Uint8Array[] = [];
  let offset = 0;

  for (const f of files) {
    const nameBytes = new TextEncoder().encode(f.name);
    const crc = crc32(f.data);
    const size = f.data.length;

    // Local file header
    const lfh = new Uint8Array(30 + nameBytes.length);
    const v = new DataView(lfh.buffer);
    v.setUint32(0, 0x04034b50, true);   // sig
    v.setUint16(4, 20, true);            // version needed
    v.setUint16(6, 0, true);             // flags
    v.setUint16(8, 0, true);             // compression (stored)
    v.setUint16(10, 0, true); v.setUint16(12, 0, true); // mod time/date
    v.setUint32(14, crc, true);
    v.setUint32(18, size, true);
    v.setUint32(22, size, true);
    v.setUint16(26, nameBytes.length, true);
    v.setUint16(28, 0, true);
    lfh.set(nameBytes, 30);

    // Central directory entry
    const cde = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cde.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
    cv.setUint16(8, 0, true); cv.setUint16(10, 0, true);
    cv.setUint16(12, 0, true); cv.setUint16(14, 0, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint16(30, 0, true); cv.setUint16(32, 0, true);
    cv.setUint16(34, 0, true); cv.setUint32(36, 0, true);
    cv.setUint32(42, offset, true);
    cde.set(nameBytes, 46);

    parts.push(lfh, f.data);
    centralDir.push(cde);
    offset += lfh.length + size;
  }

  const cdStart = offset;
  let cdSize = 0;
  centralDir.forEach(cd => cdSize += cd.length);

  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true); ev.setUint16(6, 0, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, cdStart, true);
  ev.setUint16(20, 0, true);

  const total = [...parts, ...centralDir, eocd];
  const len = total.reduce((s, a) => s + a.length, 0);
  const result = new Uint8Array(len);
  let pos = 0;
  for (const t of total) { result.set(t, pos); pos += t.length; }
  return result;
}

function crc32(data: Uint8Array): number {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < data.length; i++) {
    crc ^= data[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
    }
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

/** Download data as a proper .xlsx file */
export function exportToExcel(data: any[], filename: string): void {
  if (!data || !data.length) return;
  const bytes = buildXlsx(data);
  const blob = new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
