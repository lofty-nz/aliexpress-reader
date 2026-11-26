#!/usr/bin/env python3
"""AliExpress Reader — pulls orders out of a printed AliExpress "Orders" page (PDF printed from the browser).

Reads word positions with poppler's pdftotext -bbox-layout (no OCR, no AI), so the left menu and the
right-hand buttons (Details, Add to cart, Remove, ...) never get mixed into the order text.

Money is in cents (int) and dates are ISO (YYYY-MM-DD), the same as Statement Teacher and Money Trail.

    python3 reader.py output.pdf                 # print the orders
    python3 reader.py output.pdf --export DIR    # write Statement Teacher-shaped files into DIR
"""
import csv
import html
import json
import re
import subprocess
import unicodedata
import sys
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
LAYOUT = "AliExpress orders list"

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"^Date:\s*([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})")
REF_RE = re.compile(r"(?:Ref\.?\s*Number|Order\s*(?:ID|number))\s*:?\s*(\d{8,})", re.I)
CUR = r"(?P<cur>[A-Z]{0,3}\s?\$|€|£|¥|₩|R\$|zł)"
NUM = r"(?P<n>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
TOTAL_RE = re.compile(r"Total\s*:?\s*" + CUR + r"\s?" + NUM, re.I)
PRICE_RE = re.compile(r"^" + CUR + r"\s?" + NUM + r"\s*[x×]\s*(?P<q>\d+)$")
# right-hand buttons and page furniture inside an order (never item text)
BUTTONS = re.compile(r"^(Details|Copy|Write a review|Add to cart|Remove|Need help\?|Buy (it )?again|Track order|Confirm received|"
                     r"Pay now|Delete|Cancel order|Return/refund|Open dispute|Add review|View details|Contact (the )?seller)$", re.I)
# small print under an item: kept as the item's tags, never an item
TAG_RE = re.compile(r"(coupon if delayed|free returns|free shipping|choice|bundle deals?|delivery guarantee|price adjustment|"
                    r"fast delivery|\d+-day delivery|refund if|plus\b)", re.I)
STATUSES = ("Completed", "Awaiting delivery", "Awaiting shipment", "Shipped", "Processing", "Processed", "To pay", "Closed",
            "Cancelled", "Canceled", "Refunded", "Order closed", "Awaiting payment", "In transit", "Delivered", "Finished",
            "To ship", "To receive", "Refund in progress", "Dispute in progress")
PAGE_GAP = 10000.0   # pages are stacked into one long strip so an order split over a page break stays whole


def money(cur, n):
    """("NZ$ ", "1,234.5") -> ("NZ$", 123450)"""
    return re.sub(r"\s", "", cur), round(float(n.replace(",", "")) * 100)


def pdf_lines(path):
    """Every text line in the PDF: [{page, x0, y0, x1, y1, y (stacked), text}] from pdftotext -bbox-layout."""
    out = subprocess.run(["pdftotext", "-bbox-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    lines = []
    for pno, page in enumerate(re.findall(r"<page\b.*?</page>", out, re.S), 1):
        for m in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', page, re.S):
            words = [unicodedata.normalize("NFKC", html.unescape(w)).replace("...", "…") for w in re.findall(r">([^<]*)</word>", m.group(5))]
            text = " ".join(w for w in words if w).strip()
            if text:
                x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
                lines.append({"page": pno, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "y": (pno - 1) * PAGE_GAP + y0, "text": text})
    return lines


def page_sizes(path):
    """{page: (width, height)} in points."""
    info = subprocess.run(["pdfinfo", "-f", "1", "-l", "9999", str(path)], capture_output=True, text=True).stdout
    sizes = {int(a): (float(b), float(c)) for a, b, c in re.findall(r"Page\s+(\d+)\s+size:\s+([\d.]+) x ([\d.]+)", info)}
    if not sizes:
        m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
        n = int((re.search(r"Pages:\s+(\d+)", info) or [0, 1])[1])
        sizes = {p: (float(m[1]), float(m[2])) for p in range(1, n + 1)} if m else {}
    return sizes


def iso(mon, day, year):
    m = MONTHS.get(mon[:3].lower())
    return f"{int(year):04d}-{m:02d}-{int(day):02d}" if m else ""


def columns(lines):
    """Per page: (left, right) x edges of the order area. left = the status column (anything further left is the
    site's side menu), right = the Total/buttons column (anything at or right of it is not order text)."""
    cols = {}
    for p in {ln["page"] for ln in lines}:
        on = [ln for ln in lines if ln["page"] == p]
        dates = [ln for ln in on if DATE_RE.match(ln["text"])]
        status = [ln for ln in on if any(ln["text"].lower() == s.lower() for s in STATUSES)
                  and any(abs(ln["y0"] - d["y0"]) < 14 for d in dates)]
        totals = [ln for ln in on if TOTAL_RE.search(ln["text"])]
        refs = [ln for ln in on if REF_RE.search(ln["text"])]
        left = min((s["x0"] for s in status), default=None)
        right = min([t["x0"] for t in totals] + [r["x0"] for r in refs] + [d["x0"] for d in dates], default=None)
        cols[p] = (left, right)
    pages = sorted(cols)
    for p in pages:                      # a page with no status/total (e.g. only the tail of an order) borrows a neighbour's
        l, r = cols[p]
        near = [cols[q] for q in sorted(pages, key=lambda q: abs(q - p)) if q != p]
        cols[p] = (l if l is not None else next((c[0] for c in near if c[0] is not None), 0.0),
                   r if r is not None else next((c[1] for c in near if c[1] is not None), 1e9))
    return cols


def read_lines(lines):
    """Text lines (from pdf_lines or made up in tests) -> list of orders, newest first as printed."""
    lines = sorted(lines, key=lambda ln: (ln["y"], ln["x0"]))
    cols = columns(lines)
    starts = [i for i, ln in enumerate(lines) if DATE_RE.match(ln["text"])]
    orders = []
    for n, i in enumerate(starts):
        top = lines[i]["y"] - 8                     # status sits a few points below/above the Date line
        bottom = lines[starts[n + 1]]["y"] - 8 if n + 1 < len(starts) else float("inf")
        block = [ln for ln in lines if top <= ln["y"] < bottom]
        orders.append(read_order(block, lines[i], cols))
    return orders


def read_order(block, date_line, cols):
    d = DATE_RE.match(date_line["text"])
    o = {"ref": "", "date": iso(*d.groups()), "dateText": date_line["text"][5:].strip(), "status": "", "store": "",
         "currency": "", "total": None, "items": [], "itemsTotal": None, "extra": None, "page": date_line["page"],
         "pages": sorted({ln["page"] for ln in block}), "box": None, "flags": [], "notes": []}
    body = []
    for ln in block:
        left, right = cols[ln["page"]]
        t = ln["text"]
        if ln is date_line:
            continue
        m = REF_RE.search(t)
        if m and not o["ref"]:
            o["ref"] = m.group(1)
            continue
        m = TOTAL_RE.search(t)
        if m and o["total"] is None:
            o["currency"], o["total"] = money(m["cur"], m["n"])
            continue
        if any(t.lower() == s.lower() for s in STATUSES) and not o["status"]:
            o["status"] = t
            continue
        if ln["x0"] < left - 5 or ln["x0"] >= right - 5 or BUTTONS.match(t):
            continue                                 # side menu, right-hand column, buttons
        body.append(ln)
    if body:
        o["store"] = body.pop(0)["text"]             # first line under the status = the store
    item = None
    pending = []                                     # title/variant lines waiting for their price line
    for ln in body:
        t = ln["text"]
        m = PRICE_RE.match(t)
        if m:
            cur, unit = money(m["cur"], m["n"])
            qty = int(m["q"])
            title = pending[0] if pending else ""
            item = {"title": title, "variant": " · ".join(pending[1:]), "unitPrice": unit, "qty": qty, "amount": unit * qty,
                    "currency": cur, "tags": [], "truncated": title.endswith("…") or title.endswith("...")}
            o["items"].append(item)
            pending = []
        elif TAG_RE.search(t) and not pending:
            if item:
                item["tags"].append(t)
        else:
            pending.append(t)
    if pending:                                      # text with no price line after it: keep it, don't guess an amount
        o["notes"].append("text without a price: " + " / ".join(pending))
    ys = [ln for ln in block]
    o["box"] = {"page": date_line["page"], "y0": min(ln["y0"] for ln in ys if ln["page"] == date_line["page"]) - 6,
                "y1": max(ln["y1"] for ln in ys if ln["page"] == date_line["page"]) + 6}
    check(o)
    return o


def check(o):
    """Flags (machine words) + notes (plain words) for things worth a look."""
    if not o["ref"]:
        o["flags"].append("noref")
        o["notes"].append("no order number found")
    if o["total"] is None:
        o["flags"].append("nototal")
        o["notes"].append("no total found")
    if not o["store"]:
        o["flags"].append("nostore")
    if not o["items"]:
        o["flags"].append("itemsnotlisted")
        o["notes"].append("items not named on the Orders page (usually an order with several items) — open Details on AliExpress to see them")
        return
    o["itemsTotal"] = sum(i["amount"] for i in o["items"])
    if o["total"] is not None:
        o["extra"] = o["total"] - o["itemsTotal"]
        if o["extra"] > 0:
            o["notes"].append(f"total is {o['extra'] / 100:.2f} more than the items shown (shipping, GST, fees)")
        elif o["extra"] < 0:
            o["notes"].append(f"total is {-o['extra'] / 100:.2f} less than the items (discount, coupon or part refund)")
    if len(o["items"]) == 1 and o["items"][0]["truncated"]:
        o["notes"].append("item name cut short on the page (ends with …)")
    if len(o["pages"]) > 1:
        o["notes"].append(f"split over pages {o['pages'][0]}–{o['pages'][-1]}")


def read_pdf(path):
    path = Path(path)
    lines = pdf_lines(path)
    orders = read_lines(lines)
    sizes = page_sizes(path)
    warnings = []
    if not orders:
        warnings.append("No orders found. Is this a printed AliExpress Orders page (Account → Orders, then Print → Save as PDF)?")
    refs = [o["ref"] for o in orders if o["ref"]]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    if dup:
        warnings.append("Same order number twice: " + ", ".join(dup))
    for o in orders:
        if o["ref"] in dup:
            o["flags"].append("duplicate")
    return {"file": path.name, "pages": len(sizes) or max((ln["page"] for ln in lines), default=0),
            "pageSizes": {str(k): v for k, v in sizes.items()}, "orders": orders, "warnings": warnings,
            "read": datetime.now().isoformat(timespec="seconds"), "by": "AliExpress Reader " + VERSION}


# ---------------- export: Statement Teacher's shapes (see README) ----------------

def cents(v):
    return "" if v is None else f"{v / 100:.2f}"


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "-", s).strip()[:120] or "file"


def order_text(o):
    n = len(o["items"])
    what = (o["items"][0]["title"] if n == 1 else f"{n} items" if n else "items not listed")
    return f"AliExpress · {o['store'] or '?'} · order {o['ref'] or '?'} · {what}"


def order_doc(o, res):
    """One order as a Statement Teacher invoice document (same keys as its <name>.json)."""
    lines = [{"page": o["page"], "date": o["date"], "text": (i["title"] + (" — " + i["variant"] if i["variant"] else "")),
              "accts": [], "amount": i["amount"], "balance": None, "kind": "item", "flags": [],
              "qty": i["qty"], "unitPrice": i["unitPrice"], "tags": i["tags"]} for i in o["items"]]
    if o["extra"]:
        lines.append({"page": o["page"], "date": o["date"], "text": "shipping / GST / fees" if o["extra"] > 0 else "discount / coupon",
                      "accts": [], "amount": o["extra"], "balance": None, "kind": "item", "flags": ["worked out"]})
    adds = None if o["total"] is None or not o["items"] else sum(ln["amount"] for ln in lines) == o["total"]
    facts = {"total": o["total"], "date": o["date"], "issuer": f"AliExpress – {o['store']}" if o["store"] else "AliExpress",
             "invoiceNo": o["ref"], "layout": LAYOUT, "currency": o["currency"], "status": o["status"]}
    return {"file": res["file"], "documentId": f"aliexpress-{o['ref']}", "approved": False, "group": "AliExpress",
            "layout": LAYOUT, "docType": "invoice", "case": {},
            "fields": {"invoiceNumber": {"label": "Order number", "value": o["ref"], "text": o["ref"], "how": "aliexpress"},
                       "invoiceDate": {"label": "Order date", "value": o["date"], "text": o["dateText"], "how": "aliexpress"},
                       "amountDue": {"label": "Total", "value": o["total"], "text": cents(o["total"]), "how": "aliexpress"},
                       "biller": {"label": "Store", "value": o["store"], "text": o["store"], "how": "aliexpress"}},
            "facts": facts, "accounts": [], "check": {"ok": adds, "lines": len(lines), "notes": o["notes"], "flags": o["flags"]},
            "lines": lines, "readers": [{"page": p, "tags": ["text"]} for p in o["pages"]],
            "made": datetime.now().isoformat(timespec="seconds"), "by": "AliExpress Reader " + VERSION, "rating": None, "dnum": "",
            "aliexpress": o}


def list_doc(res):
    """The whole printed list as one statement-like document: one money-out Line per order (amount negative)."""
    lines = [{"page": o["page"], "date": o["date"], "text": order_text(o), "accts": [],
              "amount": None if o["total"] is None else -o["total"], "balance": None, "kind": "txn",
              "flags": [f for f in o["flags"] if f != "itemsnotlisted"], "ref": o["ref"], "orderRef": o["ref"]} for o in res["orders"]]
    dates = sorted(o["date"] for o in res["orders"] if o["date"])
    return {"file": res["file"], "documentId": "aliexpress-list-" + _safe(Path(res["file"]).stem), "approved": False, "group": "AliExpress",
            "layout": LAYOUT, "docType": "orders", "case": {},
            "fields": {"periodFrom": {"label": "First order", "value": dates[0] if dates else None, "text": dates[0] if dates else "", "how": "aliexpress"},
                       "periodTo": {"label": "Last order", "value": dates[-1] if dates else None, "text": dates[-1] if dates else "", "how": "aliexpress"}},
            "facts": {"total": sum(o["total"] or 0 for o in res["orders"]), "date": dates[-1] if dates else "", "issuer": "AliExpress",
                      "layout": LAYOUT, "orders": len(res["orders"])},
            "accounts": [], "check": {"ok": None, "lines": len(lines)}, "lines": lines,
            "readers": [{"page": p, "tags": ["text"]} for p in range(1, res["pages"] + 1)],
            "made": datetime.now().isoformat(timespec="seconds"), "by": "AliExpress Reader " + VERSION, "rating": None, "dnum": ""}


def export(res, folder):
    """Write the Statement Teacher-shaped files -> {folder, count}."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe("AliExpress orders - " + Path(res["file"]).stem)
    ld = list_doc(res)
    (folder / f"{stem}.json").write_text(json.dumps(ld, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(folder / f"{stem} - lines.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "details", "amount", "balance", "kind", "page", "flags", "doubtful amount"])
        for ln in ld["lines"]:
            w.writerow([ln["date"], ln["text"], cents(ln["amount"]), "", ln["kind"], ln["page"], " ".join(ln["flags"]), ""])
    with open(folder / "all-transactions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "account", "date", "details", "amount", "balance", "flags", "D-number", "page reference", "Description ID",
                    "transfer", "supporting documents", "doubtful amount"])
        for o, ln in zip(res["orders"], ld["lines"]):
            w.writerow([res["file"], "AliExpress", ln["date"], ln["text"], cents(ln["amount"]), "", " ".join(ln["flags"]), "",
                        f"p{o['page']}", "", "", f"AliExpress order {o['ref']}.json" if o["ref"] else "", ""])
    docs = []
    for o in res["orders"]:
        name = f"AliExpress order {o['ref'] or o['date']}"
        d = order_doc(o, res)
        (folder / f"{_safe(name)}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        docs.append([res["file"], "invoice", LAYOUT, "no", "", "", "", "", "", {True: "yes", False: "NO"}.get(d["check"]["ok"], ""),
                     len(d["lines"]), cents(o["total"]), o["date"], d["facts"]["issuer"], f"{_safe(name)}.json", "", "", "", "", "", "", "text"])
    with open(folder / "documents.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "type", "layout", "approved", "account", "from", "to", "opening", "closing", "adds up", "lines", "total", "date",
                    "from (issuer)", "details file", "rating", "rating reason", "rating note", "D-number", "merged names", "in credit", "readers"])
        w.writerows(docs)
    with open(folder / "items.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["order date", "order number", "store", "status", "item", "option", "unit price", "qty", "amount", "currency",
                    "order total", "order extra (shipping/GST/discount)", "notes"])
        for o in res["orders"]:
            for i in o["items"] or [None]:
                w.writerow([o["date"], o["ref"], o["store"], o["status"], i["title"] if i else "(items not listed on this page)",
                            i["variant"] if i else "", cents(i["unitPrice"]) if i else "", i["qty"] if i else "",
                            cents(i["amount"]) if i else "", o["currency"], cents(o["total"]), cents(o["extra"]), "; ".join(o["notes"])])
    (folder / "README.txt").write_text(
        f"Read by AliExpress Reader {VERSION} on {datetime.now():%d %b %Y %H:%M} from {res['file']}\n\n"
        f"{len(res['orders'])} orders. Same file shapes as a Statement Teacher export (money in cents in the .json files,\n"
        "dollars in the .csv files, dates YYYY-MM-DD):\n"
        f"  {stem}.json — the whole list as one document: one Line per order, amount NEGATIVE (money out), kind txn,\n"
        "      ref = the AliExpress order number. This is what lines up with the card/bank statement.\n"
        "  AliExpress order <number>.json — each order as an invoice document: facts.total, facts.invoiceNo (order number),\n"
        "      facts.issuer (AliExpress – store); its Lines are the items (amount POSITIVE = cost, qty, unitPrice), plus a\n"
        "      worked-out 'shipping / GST / fees' or 'discount' Line so the Lines add up to the total.\n"
        "  all-transactions.csv, documents.csv, <list> - lines.csv — same columns as Statement Teacher's.\n"
        "  items.csv — one row per item (handy as a spreadsheet).\n\n"
        "Orders with several items show no item names on the Orders list page, so their items aren't named here\n"
        "(flag itemsnotlisted) — the order total is still right.\n", encoding="utf-8")
    return {"folder": str(folder), "count": len(res["orders"])}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    res = read_pdf(argv[1])
    if "--export" in argv:
        out = argv[argv.index("--export") + 1]
        print(json.dumps(export(res, out)))
        return 0
    if "--json" in argv:
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    for o in res["orders"]:
        print(f"{o['date']}  {o['ref']:<17} {o['status']:<10} {cents(o['total']):>8} {o['currency']:<4} {o['store']}")
        for i in o["items"]:
            print(f"      {i['qty']:>3} × {cents(i['unitPrice']):>7} = {cents(i['amount']):>8}  {i['title']}  [{i['variant']}]")
        for nt in o["notes"]:
            print("      ! " + nt)
    for w in res["warnings"]:
        print("WARNING: " + w)
    print(f"{len(res['orders'])} orders, total {cents(sum(o['total'] or 0 for o in res['orders']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
