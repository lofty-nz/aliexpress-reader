"""Xero export: each AliExpress order becomes one Xero BILL (accounts payable) from the contact "AliExpress".

- xero_csv(res, opts)  -> text for Xero's bill import (Business → Bills to pay → Import), columns as in Xero's template.
- xero_json(res, opts) -> body for the Xero Accounting API: POST https://api.xero.com/api.xro/2.0/Invoices (Type ACCPAY).

Rules (same in web/xero.mjs):
- Cancelled / closed / refunded / expired orders are left out (nothing was paid).
- Invoice number = the AliExpress order number; date and due date = the order date (it's already paid).
- Lines = the items (qty × unit price); the difference to the order total (shipping, GST, fees, or a discount) is its own
  line, so every bill adds up to exactly what the card was charged. Orders with no item names = one line for the total.
- Amounts are what AliExpress charged (GST included if any). opts.tax: "none" (default: No GST, LineAmountTypes NoTax)
  or "gst" (GST on Expenses 15%, amounts tax inclusive). Status DRAFT so nothing is approved without a look.
"""
import csv
import io
import json
from datetime import date

DEFAULTS = {"contact": "AliExpress", "account": "300", "tax": "none", "status": "DRAFT"}
CURRENCIES = {"NZ$": "NZD", "US$": "USD", "A$": "AUD", "AU$": "AUD", "C$": "CAD", "CA$": "CAD", "€": "EUR", "£": "GBP", "¥": "JPY"}
HEADERS = ["*ContactName", "EmailAddress", "POAddressLine1", "POAddressLine2", "POAddressLine3", "POAddressLine4", "POCity", "PORegion",
           "POPostalCode", "POCountry", "*InvoiceNumber", "*InvoiceDate", "*DueDate", "InventoryItemCode", "Description", "*Quantity",
           "*UnitAmount", "*AccountCode", "*TaxType", "TrackingName1", "TrackingOption1", "TrackingName2", "TrackingOption2", "Currency"]


def _opts(opts):
    o = dict(DEFAULTS)
    o.update({k: v for k, v in (opts or {}).items() if v not in (None, "")})
    return o


def bill_lines(o):
    """[(description, quantity, unit amount in cents)] adding up to the order total."""
    store = o["store"] or "AliExpress store"
    if not o["items"]:
        return [(f"{store}: order {o['ref']} (several items, not named on the Orders page)", 1, o["total"] or 0)]
    out = [(f"{store}: {i['title']}" + (f" ({i['variant']})" if i["variant"] else ""), i["qty"], i["unitPrice"]) for i in o["items"]]
    if o["extra"]:
        out.append(("Shipping, GST and fees" if o["extra"] > 0 else "Discount / coupon", 1, o["extra"]))
    return out


def bills(res):
    return [o for o in res["orders"] if "cancelled" not in o["flags"] and o["total"] is not None]


def nz_date(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""


def xero_csv(res, opts=None):
    op = _opts(opts)
    tax = "GST on Expenses" if op["tax"] == "gst" else "No GST"
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADERS)
    for o in bills(res):
        for desc, qty, unit in bill_lines(o):
            row = dict.fromkeys(HEADERS, "")
            row.update({"*ContactName": op["contact"], "*InvoiceNumber": o["ref"], "*InvoiceDate": nz_date(o["date"]), "*DueDate": nz_date(o["date"]),
                        "Description": desc, "*Quantity": qty, "*UnitAmount": f"{unit / 100:.2f}", "*AccountCode": op["account"],
                        "*TaxType": tax, "Currency": CURRENCIES.get(o["currency"], "")})
            w.writerow([row[h] for h in HEADERS])
    return out.getvalue()


def xero_json(res, opts=None):
    op = _opts(opts)
    gst = op["tax"] == "gst"
    inv = []
    for o in bills(res):
        b = {"Type": "ACCPAY", "Contact": {"Name": op["contact"]}, "InvoiceNumber": o["ref"], "Reference": o["store"],
             "Date": o["date"], "DueDate": o["date"], "Status": op["status"], "LineAmountTypes": "Inclusive" if gst else "NoTax",
             "LineItems": [{"Description": d, "Quantity": q, "UnitAmount": round(u / 100, 2), "AccountCode": op["account"],
                            "TaxType": "INPUT2" if gst else "NONE"} for d, q, u in bill_lines(o)]}
        if CURRENCIES.get(o["currency"]):
            b["CurrencyCode"] = CURRENCIES[o["currency"]]
        inv.append(b)
    return json.dumps({"Invoices": inv}, indent=1, ensure_ascii=False)
