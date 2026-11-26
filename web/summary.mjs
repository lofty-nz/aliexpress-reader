// PDF summary drawn with jsPDF (window.jspdf.jsPDF in the browser). Same page as summary.py: tiles, by month, every order.
import {byMonth, spent} from "./reader.mjs";

const ACCENT = [116, 160, 30], INK = [28, 28, 26], MUTE = [107, 107, 102], LINE = [227, 225, 220], WARN = [178, 106, 0];
const WINANSI_EXTRA = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ";
// the built-in PDF fonts only have Latin-1 + a few: swap the rest for something close
const safe = s => String(s ?? "").replace(/−/g, "-").replace(/⚠\s?/g, "! ").replace(/[^\x20-\x7e\xa0-\xff]/g,
  c => WINANSI_EXTRA.includes(c) ? c : "?");
const money = c => c == null ? "-" : (c < 0 ? "-" : "") + "$" + (Math.abs(c) / 100).toLocaleString("en-NZ", {minimumFractionDigits: 2, maximumFractionDigits: 2});

export function summaryPdf(res, jsPDF) {
  const doc = new jsPDF({unit: "pt", format: "a4"});
  const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight(), M = 40;
  let page = 1, y = M;
  const os = res.orders, total = os.reduce((a, o) => a + spent(o), 0);
  const dates = os.map(o => o.date).filter(Boolean).sort();
  const cur = os[0]?.currency || "";
  doc.setProperties({title: `AliExpress orders - ${safe(res.file)}`, creator: "AliExpress Reader"});

  const text = (x, yy, s, size = 9, bold = false, colour = INK, opts = {}) => {
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(...colour);
    let t = safe(s);
    if (opts.width) while (t.length > 2 && doc.getTextWidth(t) > opts.width) t = t.slice(0, -2) + "…";
    doc.text(t, x, yy, opts.right ? {align: "right"} : undefined);
  };
  const wrap = (s, width, size) => { doc.setFont("helvetica", "normal"); doc.setFontSize(size); return doc.splitTextToSize(safe(s), width); };
  const rule = yy => { doc.setDrawColor(...LINE); doc.setLineWidth(0.6); doc.line(M, yy, W - M, yy); };
  const footer = () => { text(M, H - 24, "AliExpress Reader - testtagrepair.co.nz", 7, false, MUTE); text(W - M, H - 24, `page ${page}`, 7, false, MUTE, {right: true}); };
  const need = (h, header) => {
    if (y + h > H - M - 14) { footer(); doc.addPage(); page++; y = M; if (header) header(); }
  };

  doc.setFillColor(...ACCENT); doc.rect(0, 0, W, 8, "F");
  text(M, 52, "AliExpress orders", 22, true);
  text(M, 70, `From ${res.file} - read ${new Date().toLocaleDateString("en-NZ", {day: "numeric", month: "short", year: "numeric"})}`, 9, false, MUTE);
  const tiles = [["Orders", String(os.length)], [`Total spent (${cur})`, money(total)], ["First order", dates[0] || "-"],
    ["Last order", dates.at(-1) || "-"], ["Items not named", String(os.filter(o => o.flags.includes("itemsnotlisted")).length)]];
  const tw = (W - 2 * M - 4 * 8) / 5;
  tiles.forEach(([label, val], k) => {
    const x = M + k * (tw + 8);
    doc.setFillColor(247, 246, 243); doc.rect(x, 86, tw, 46, "F");
    text(x + 8, 101, label, 7.5, false, MUTE);
    text(x + 8, 122, val, val.length < 11 ? 14 : 11, true);
  });
  y = 156;
  const months = byMonth(res);
  if (months.size) {
    text(M, y, "By month", 11, true); y += 14;
    const biggest = Math.max(...[...months.values()].map(v => v[1])) || 1;
    for (const [k, [n, t]] of months) {
      need(14);
      text(M, y + 9, k, 8.5);
      doc.setFillColor(...ACCENT); doc.rect(M + 60, y + 1, Math.max(0.5, (W - 2 * M - 190) * t / biggest), 10, "F");
      text(W - M - 70, y + 9, `${n} order${n !== 1 ? "s" : ""}`, 8, false, MUTE);
      text(W - M, y + 9, money(t), 8.5, true, INK, {right: true});
      y += 14;
    }
    y += 12;
  }
  const cols = [["Date", M, 52], ["Order no.", M + 54, 86], ["Store", M + 142, 110], ["Items", M + 254, 170]], rx = W - M;
  const header = () => {
    if (page === 1) { text(M, y + 9, "Orders", 11, true); y += 16; }
    for (const [name, x] of cols) text(x, y + 8, name, 7.5, true, MUTE);
    text(rx - 48, y + 8, "Extra", 7.5, true, MUTE, {right: true});
    text(rx, y + 8, "Total", 7.5, true, MUTE, {right: true});
    y += 12; rule(y); y += 4;
  };
  need(60); header();
  for (const o of os) {
    let items = [];
    for (const i of o.items) items.push(...wrap(`${i.qty} × ${money(i.unitPrice)}  ${i.title}` + (i.variant ? ` (${i.variant})` : ""), cols[3][2], 7.5));
    if (!o.items.length) items = ["(not named on the Orders page)"];
    const store = wrap(o.store, cols[2][2], 8);
    const notes = o.notes.filter(n => !/cut short|not named|more than the items/.test(n));
    const h = Math.max(items.length * 10, store.length * 10, 20) + notes.length * 10 + 6;
    need(h, header);
    const y0 = y + 9;
    text(M, y0, o.date, 8); text(M, y0 + 10, o.status, 6.5, false, MUTE);
    text(cols[1][1], y0, o.ref, 7.5);
    store.forEach((s, k) => text(cols[2][1], y0 + 10 * k, s, 8));
    items.forEach((s, k) => text(cols[3][1], y0 + 10 * k, s, 7.5, false, o.items.length ? MUTE : WARN));
    notes.forEach((s, k) => text(cols[3][1], y0 + 10 * (items.length + k), "! " + s, 7, false, WARN, {width: W - M - cols[3][1]}));
    if (o.extra != null) text(rx - 48, y0, money(o.extra), 8, false, MUTE, {right: true});
    const gone = o.flags.includes("cancelled");
    text(rx, y0, money(o.total), 8.5, !gone, gone ? MUTE : INK, {right: true});
    if (gone) { const w = doc.getTextWidth(money(o.total)); doc.setDrawColor(...MUTE); doc.line(rx - w, y0 - 3, rx, y0 - 3); }
    y += h; rule(y - 3);
  }
  need(30); y += 6;
  text(cols[3][1], y + 8, `${os.length} orders`, 9, true);
  text(rx, y + 8, money(total), 11, true, ACCENT, {right: true});
  y += 26; need(30);
  for (const s of wrap("Extra = order total minus the items shown: shipping, GST and fees (minus = a discount). Cancelled, closed and expired " +
    "orders are listed but left out of the totals. Orders with several items don't name them on AliExpress's Orders page; their totals are still right.", W - 2 * M, 7)) {
    text(M, y, s, 7, false, MUTE); y += 9;
  }
  footer();
  return doc;
}
