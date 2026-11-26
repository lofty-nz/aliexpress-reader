// Xero export (same rules as xero.py): each order that was paid = one Xero bill from "AliExpress", lines add up to the total.
export const DEFAULTS = {contact: "AliExpress", account: "300", tax: "none", status: "DRAFT"};
const CURRENCIES = {"NZ$": "NZD", "US$": "USD", "A$": "AUD", "AU$": "AUD", "C$": "CAD", "CA$": "CAD", "€": "EUR", "£": "GBP", "¥": "JPY"};
const HEADERS = ["*ContactName", "EmailAddress", "POAddressLine1", "POAddressLine2", "POAddressLine3", "POAddressLine4", "POCity", "PORegion",
  "POPostalCode", "POCountry", "*InvoiceNumber", "*InvoiceDate", "*DueDate", "InventoryItemCode", "Description", "*Quantity",
  "*UnitAmount", "*AccountCode", "*TaxType", "TrackingName1", "TrackingOption1", "TrackingName2", "TrackingOption2", "Currency"];

const opt = o => ({...DEFAULTS, ...Object.fromEntries(Object.entries(o || {}).filter(([, v]) => v !== "" && v != null))});
const nzDate = iso => iso ? iso.split("-").reverse().join("/") : "";
export const bills = res => res.orders.filter(o => !o.flags.includes("cancelled") && o.total != null);

export function billLines(o) {
  const store = o.store || "AliExpress store";
  if (!o.items.length) return [[`${store}: order ${o.ref} (several items, not named on the Orders page)`, 1, o.total || 0]];
  const out = o.items.map(i => [`${store}: ${i.title}` + (i.variant ? ` (${i.variant})` : ""), i.qty, i.unitPrice]);
  if (o.extra) out.push([o.extra > 0 ? "Shipping, GST and fees" : "Discount / coupon", 1, o.extra]);
  return out;
}

export function xeroCsv(res, opts) {
  const op = opt(opts), tax = op.tax === "gst" ? "GST on Expenses" : "No GST";
  const q = v => { const s = String(v ?? ""); return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const rows = [HEADERS];
  for (const o of bills(res)) for (const [d, qty, unit] of billLines(o)) {
    const r = Object.fromEntries(HEADERS.map(h => [h, ""]));
    Object.assign(r, {"*ContactName": op.contact, "*InvoiceNumber": o.ref, "*InvoiceDate": nzDate(o.date), "*DueDate": nzDate(o.date),
      Description: d, "*Quantity": qty, "*UnitAmount": (unit / 100).toFixed(2), "*AccountCode": op.account, "*TaxType": tax,
      Currency: CURRENCIES[o.currency] || ""});
    rows.push(HEADERS.map(h => r[h]));
  }
  return rows.map(r => r.map(q).join(",")).join("\r\n") + "\r\n";
}

export function xeroJson(res, opts) {
  const op = opt(opts), gst = op.tax === "gst";
  const Invoices = bills(res).map(o => {
    const b = {Type: "ACCPAY", Contact: {Name: op.contact}, InvoiceNumber: o.ref, Reference: o.store, Date: o.date, DueDate: o.date,
      Status: op.status, LineAmountTypes: gst ? "Inclusive" : "NoTax",
      LineItems: billLines(o).map(([d, q, u]) => ({Description: d, Quantity: q, UnitAmount: Math.round(u) / 100, AccountCode: op.account,
        TaxType: gst ? "INPUT2" : "NONE"}))};
    if (CURRENCIES[o.currency]) b.CurrencyCode = CURRENCIES[o.currency];
    return b;
  });
  return JSON.stringify({Invoices}, null, 1);
}
