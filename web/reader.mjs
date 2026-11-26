// AliExpress Reader — browser version of reader.py (same rules, same results). Reads a printed AliExpress "Orders"
// page PDF with pdf.js, entirely in the browser: the file is never uploaded. Money in cents, dates YYYY-MM-DD.
// Works in the browser and in node (tests): pass pdf.js in.

export const VERSION = "1.3.0";

const MONTHS = {jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12};
const DATE_RE = /^Date:\s*([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/;
const REF_RE = /(?:Ref\.?\s*Number|Order\s*(?:ID|number))\s*:?\s*(\d{8,})/i;
const CUR = String.raw`(?<cur>[A-Z]{0,3}\s?\$|€|£|¥|₩|R\$|zł)`;
const NUM = String.raw`(?<n>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)`;
const TOTAL_RE = new RegExp(String.raw`Total\s*:?\s*` + CUR + String.raw`\s?` + NUM, "i");
const PRICE_RE = new RegExp("^" + CUR + String.raw`\s?` + NUM + String.raw`\s*[x×]\s*(?<q>\d+)$`);
const BUTTONS = /^(Details|Copy|Write a review|Add to cart|Remove|Need help\?|Buy (it )?again|Track order|Confirm received|Pay now|Delete|Cancel order|Return\/refund|Open dispute|Add review|View details|Contact (the )?seller)$/i;
const TAG_RE = /(coupon if delayed|for delivery issue|free returns|free shipping|choice|bundle deals?|delivery guarantee|price adjustment|fast delivery|\d+-day delivery|refund if|plus\b)/i;
const STATUSES = ["Completed", "Awaiting delivery", "Awaiting shipment", "Shipped", "Processing", "Processed", "To pay", "Closed",
  "Cancelled", "Canceled", "Refunded", "Order closed", "Awaiting payment", "In transit", "Delivered", "Finished",
  "To ship", "To receive", "Refund in progress", "Dispute in progress", "Expired"].map(s => s.toLowerCase());
const END_RE = /^(More to love|You may also like|Recommended for you|Recommended)$|All rights reserved/i;
const REFUND_RE = /refund/i;
const NOT_SPENT = /^(cancell?ed|closed|order closed|refunded|expired)$/i;
export const PAGE_GAP = 10000;

const isStatus = t => STATUSES.includes(t.toLowerCase());
const money = (cur, n) => [cur.replace(/\s/g, ""), Math.round(parseFloat(n.replace(/,/g, "")) * 100)];
export const cents = v => v == null ? "" : (v / 100).toFixed(2);
export const spent = o => o.flags.includes("cancelled") ? 0 : (o.total || 0);

function iso(mon, day, year) {
  const m = MONTHS[mon.slice(0, 3).toLowerCase()];
  return m ? `${year.padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}` : "";
}

/** pdf.js document -> {lines, sizes}. Text pieces on the same baseline and close together are joined into lines. */
export async function pdfLines(doc) {
  const lines = [], sizes = {};
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const vp = page.getViewport({scale: 1});
    sizes[p] = [vp.width, vp.height];
    const tc = await page.getTextContent();
    const bits = [];
    for (const it of tc.items) {
      if (!it.str || !it.str.trim()) continue;
      const x = it.transform[4], base = vp.height - it.transform[5], h = it.height || Math.abs(it.transform[3]) || 7;
      bits.push({x0: x, x1: x + it.width, base, h, text: it.str.normalize("NFKC").replace(/\.\.\./g, "…")});
    }
    bits.sort((a, b) => a.base - b.base || a.x0 - b.x0);
    const open = [];
    for (const b of bits) {
      const ln = open.find(l => Math.abs(l.base - b.base) < 1.5 && b.x0 - l.x1 <= l.h * 2.0 && b.x0 >= l.x0 - 1);
      if (ln) {
        ln.text += (b.x0 - ln.x1 > ln.h * 0.12 && !ln.text.endsWith(" ") ? " " : "") + b.text;
        ln.x1 = Math.max(ln.x1, b.x1);
      } else {
        open.push({...b});
      }
    }
    for (const l of open) {
      const text = l.text.replace(/\s+/g, " ").trim();
      if (text) lines.push({page: p, x0: l.x0, y0: l.base - l.h, x1: l.x1, y1: l.base, y: (p - 1) * PAGE_GAP + l.base - l.h, text});
    }
  }
  return {lines, sizes};
}

function columns(lines) {
  const cols = {};
  const pages = [...new Set(lines.map(l => l.page))].sort((a, b) => a - b);
  for (const p of pages) {
    const on = lines.filter(l => l.page === p);
    const dates = on.filter(l => DATE_RE.test(l.text));
    const status = on.filter(l => isStatus(l.text) && dates.some(d => Math.abs(l.y0 - d.y0) < 14));
    const rights = on.filter(l => TOTAL_RE.test(l.text) || REF_RE.test(l.text) || DATE_RE.test(l.text)).map(l => l.x0);
    cols[p] = [status.length ? Math.min(...status.map(s => s.x0)) : null, rights.length ? Math.min(...rights) : null];
  }
  for (const p of pages) {
    const near = pages.filter(q => q !== p).sort((a, b) => Math.abs(a - p) - Math.abs(b - p)).map(q => cols[q]);
    const [l, r] = cols[p];
    cols[p] = [l ?? near.find(c => c[0] != null)?.[0] ?? 0, r ?? near.find(c => c[1] != null)?.[1] ?? 1e9];
  }
  return cols;
}

/** text lines -> orders (newest first, as printed) */
export function readLines(lines) {
  lines = [...lines].sort((a, b) => a.y - b.y || a.x0 - b.x0);
  const end = lines.find(l => END_RE.test(l.text));
  if (end) lines = lines.filter(l => l.y < end.y - 2);
  const cols = columns(lines);
  const starts = lines.map((l, i) => DATE_RE.test(l.text) ? i : -1).filter(i => i >= 0);
  return starts.map((i, n) => {
    const top = lines[i].y - 8, bottom = n + 1 < starts.length ? lines[starts[n + 1]].y - 8 : Infinity;
    return readOrder(lines.filter(l => l.y >= top && l.y < bottom), lines[i], cols);
  });
}

function readOrder(block, dateLine, cols) {
  const d = DATE_RE.exec(dateLine.text);
  const o = {ref: "", date: iso(d[1], d[2], d[3]), dateText: dateLine.text.slice(5).trim(), status: "", store: "", currency: "",
    total: null, items: [], itemsTotal: null, extra: null, page: dateLine.page, pages: [...new Set(block.map(l => l.page))].sort((a, b) => a - b),
    box: null, flags: [], notes: [], refund: ""};
  const body = [];
  const details = block.find(l => l.text === "Details");
  for (const ln of block) {
    const [left, right] = cols[ln.page], t = ln.text;
    if (ln === dateLine) continue;
    let m = REF_RE.exec(t);
    if (m && !o.ref) { o.ref = m[1]; continue; }
    m = TOTAL_RE.exec(t);
    if (m && o.total == null) { [o.currency, o.total] = money(m.groups.cur, m.groups.n); continue; }
    if (!o.status && (isStatus(t) || (details && ln.page === details.page && Math.abs(ln.y0 - details.y0) < 6 &&
        ln.x0 >= left - 5 && ln.x0 < left + 10 && t.length < 30))) { o.status = t; continue; }
    if (REFUND_RE.test(t) && ln.x0 >= left - 5 && ln.x0 < right - 5) { o.refund = (o.refund + " " + t).trim(); continue; }
    if (ln.x0 < left - 5 || ln.x0 >= right - 5 || BUTTONS.test(t)) continue;
    body.push(ln);
  }
  if (body.length) o.store = body.shift().text;
  let item = null, pending = [];
  for (const ln of body) {
    const t = ln.text, m = PRICE_RE.exec(t);
    if (m) {
      const [cur, unit] = money(m.groups.cur, m.groups.n), qty = parseInt(m.groups.q, 10), title = pending[0] || "";
      item = {title, variant: pending.slice(1).join(" · "), unitPrice: unit, qty, amount: unit * qty, currency: cur, tags: [],
        truncated: title.endsWith("…") || title.endsWith("...")};
      o.items.push(item);
      pending = [];
    } else if (TAG_RE.test(t) && !pending.length) {
      if (item) item.tags.push(t);
    } else pending.push(t);
  }
  if (pending.length) o.notes.push("text without a price: " + pending.join(" / "));
  const here = block.filter(l => l.page === dateLine.page);
  o.box = {page: dateLine.page, y0: Math.min(...here.map(l => l.y0)) - 6, y1: Math.max(...here.map(l => l.y1)) + 6};
  check(o);
  return o;
}

function check(o) {
  if (NOT_SPENT.test(o.status || "")) {
    o.flags.push("cancelled");
    o.notes.push(`${o.status.toLowerCase()} — not counted in the totals`);
  }
  if (o.refund) {
    o.flags.push("refund");
    o.notes.push("refund: " + o.refund + (o.flags.includes("cancelled") ? "" : " — total still counted, check the refund on the statement"));
  }
  if (!o.ref) { o.flags.push("noref"); o.notes.push("no order number found"); }
  if (o.total == null) { o.flags.push("nototal"); o.notes.push("no total found"); }
  if (!o.store) o.flags.push("nostore");
  if (!o.items.length) {
    o.flags.push("itemsnotlisted");
    o.notes.push("items not named on the Orders page (usually an order with several items) — open Details on AliExpress to see them");
    return;
  }
  o.itemsTotal = o.items.reduce((a, i) => a + i.amount, 0);
  if (o.total != null) {
    o.extra = o.total - o.itemsTotal;
    if (o.extra > 0) o.notes.push(`total is ${(o.extra / 100).toFixed(2)} more than the items shown (shipping, GST, fees)`);
    else if (o.extra < 0) o.notes.push(`total is ${(-o.extra / 100).toFixed(2)} less than the items (discount, coupon or part refund)`);
  }
  if (o.items.length === 1 && o.items[0].truncated) o.notes.push("item name cut short on the page (ends with …)");
  if (o.pages.length > 1) o.notes.push(`split over pages ${o.pages[0]}–${o.pages.at(-1)}`);
}

/** pdf.js document -> result {pages, pageSizes, orders, warnings} */
export async function readPdf(doc, file = "") {
  const {lines, sizes} = await pdfLines(doc);
  const orders = readLines(lines);
  const warnings = [];
  if (!orders.length) warnings.push("No orders found. Is this a printed AliExpress Orders page (Account → Orders, then Print → Save as PDF)?");
  const refs = orders.map(o => o.ref).filter(Boolean);
  const dup = [...new Set(refs.filter((r, i) => refs.indexOf(r) !== i))].sort();
  if (dup.length) warnings.push("Same order number twice: " + dup.join(", "));
  for (const o of orders) if (dup.includes(o.ref)) o.flags.push("duplicate");
  return {file, pages: doc.numPages, pageSizes: sizes, orders, warnings, read: new Date().toISOString().slice(0, 19), by: "AliExpress Reader " + VERSION};
}

// ---------------- downloads ----------------

export function itemsText(o) {
  if (!o.items.length) return "(items not named on the Orders page)";
  return o.items.map(i => `${i.qty} × ${cents(i.unitPrice)} ${i.title}` + (i.variant ? ` (${i.variant})` : "")).join("; ");
}

/** One row per order, so the total column adds up to what was spent. */
export function ordersCsv(res) {
  const q = v => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const rows = [["date", "order number", "status", "store", "items", "items total", "extra (shipping/GST/fees, minus = discount)",
    "order total", "currency", "notes", "page"]];
  for (const o of res.orders) rows.push([o.date, o.ref, o.status, o.store, itemsText(o), cents(o.itemsTotal), cents(o.extra), cents(o.total),
    o.currency, o.notes.join("; "), o.page]);
  const total = res.orders.reduce((a, o) => a + spent(o), 0);
  rows.push([]);
  rows.push(["", "", "", `${res.orders.length} orders, total spent (cancelled left out)`, "", "", "", cents(total), res.orders[0]?.currency || "", "", ""]);
  return "﻿" + rows.map(r => r.map(q).join(",")).join("\r\n") + "\r\n";
}

/** One row per item (order details repeated). */
export function itemsCsv(res) {
  const q = v => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const rows = [["order date", "order number", "store", "status", "item", "option", "unit price", "qty", "amount", "currency", "order total"]];
  for (const o of res.orders) for (const i of o.items.length ? o.items : [null])
    rows.push([o.date, o.ref, o.store, o.status, i ? i.title : "(items not named on this page)", i?.variant || "", i ? cents(i.unitPrice) : "",
      i?.qty ?? "", i ? cents(i.amount) : "", o.currency, cents(o.total)]);
  return "﻿" + rows.map(r => r.map(q).join(",")).join("\r\n") + "\r\n";
}

export function byMonth(res) {
  const m = new Map();
  for (const o of [...res.orders].sort((a, b) => a.date < b.date ? -1 : 1)) {
    if (!o.date) continue;
    const [y, mo] = o.date.split("-");
    const k = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+mo - 1] + " " + y;
    const [n, t] = m.get(k) || [0, 0];
    m.set(k, [n + 1, t + spent(o)]);
  }
  return m;
}
