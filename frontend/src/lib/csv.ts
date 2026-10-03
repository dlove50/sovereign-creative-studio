// Small CSV reader for the Batch page: quoted fields, commas and newlines inside quotes.

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  const input = text.replace(/^﻿/, "");
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (quoted) {
      if (ch === '"' && input[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && input[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
    } else field += ch;
  }
  row.push(field);
  if (row.some((c) => c.trim() !== "")) rows.push(row);
  return rows;
}

export type BatchRowDraft = { title: string; script: string };

/** Header optional. Columns named title/script are used; otherwise 2 columns = title, script; 1 column = script. */
export function batchRowsFromCsv(text: string): BatchRowDraft[] {
  const rows = parseCsv(text);
  if (rows.length === 0) return [];
  const header = rows[0].map((c) => c.trim().toLowerCase());
  const scriptAt = header.indexOf("script");
  const hasHeader = scriptAt >= 0;
  const titleAt = hasHeader ? header.indexOf("title") : rows[0].length > 1 ? 0 : -1;
  const scriptCol = hasHeader ? scriptAt : rows[0].length > 1 ? 1 : 0;
  return rows
    .slice(hasHeader ? 1 : 0)
    .map((r) => ({ title: titleAt >= 0 ? (r[titleAt] ?? "").trim() : "", script: (r[scriptCol] ?? "").trim() }))
    .filter((r) => r.script);
}
