"""Downloads: orders CSV (one row per order) and a printable PDF summary (A4, drawn with pycairo)."""
import csv
import io
from collections import OrderedDict
from datetime import date, datetime

import cairo

from reader import cents, spent

ACCENT = (0.83, 0.22, 0.05)
INK = (0.11, 0.11, 0.1)
MUTE = (0.42, 0.42, 0.4)
LINE = (0.89, 0.88, 0.86)
WARN = (0.7, 0.42, 0.0)


def money(c):
    return "—" if c is None else ("−" if c < 0 else "") + f"${abs(c) / 100:,.2f}"


def items_text(o):
    if not o["items"]:
        return "(items not named on the Orders page)"
    return "; ".join(f"{i['qty']} × {cents(i['unitPrice'])} {i['title']}" + (f" ({i['variant']})" if i["variant"] else "") for i in o["items"])


def orders_csv(res):
    """One row per order, so the total column adds up to what was spent."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "order number", "status", "store", "items", "items total", "extra (shipping/GST/fees, minus = discount)",
                "order total", "currency", "notes", "page"])
    for o in res["orders"]:
        w.writerow([o["date"], o["ref"], o["status"], o["store"], items_text(o), cents(o["itemsTotal"]), cents(o["extra"]),
                    cents(o["total"]), o["currency"], "; ".join(o["notes"]), o["page"]])
    total = sum(spent(o) for o in res["orders"])
    w.writerow([])
    w.writerow(["", "", "", f"{len(res['orders'])} orders, total spent (cancelled left out)", "", "", "", cents(total), res["orders"][0]["currency"] if res["orders"] else "", "", ""])
    return "﻿" + out.getvalue()          # BOM so Excel/LibreOffice open the … and × characters right


def _months(res):
    m = OrderedDict()
    for o in sorted(res["orders"], key=lambda o: o["date"]):
        if o["date"]:
            k = date.fromisoformat(o["date"]).strftime("%b %Y")
            n, t = m.get(k, (0, 0))
            m[k] = (n + 1, t + spent(o))
    return m


class Doc:
    W, H, M = 595.276, 841.89, 40

    def __init__(self, fh, title):
        self.s = cairo.PDFSurface(fh, self.W, self.H)
        self.s.set_metadata(cairo.PDF_METADATA_TITLE, title)
        self.s.set_metadata(cairo.PDF_METADATA_CREATOR, "AliExpress Reader")
        self.c = cairo.Context(self.s)
        self.page = 1
        self.y = self.M

    def font(self, size, bold=False, colour=INK):
        self.c.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        self.c.set_font_size(size)
        self.c.set_source_rgb(*colour)

    def text(self, x, y, s, size=9, bold=False, colour=INK, right=False, width=None):
        self.font(size, bold, colour)
        s = str(s)
        if width:
            while s and self.c.text_extents(s).x_advance > width:
                s = s[:-2] + "…" if len(s) > 2 else ""
        if right:
            x -= self.c.text_extents(s).x_advance
        self.c.move_to(x, y)
        self.c.show_text(s)

    def wrap(self, s, width, size=8):
        self.font(size)
        lines, cur = [], ""
        for word in str(s).split():
            t = (cur + " " + word).strip()
            if self.c.text_extents(t).x_advance > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = t
        return lines + ([cur] if cur else [])

    def rule(self, y, colour=LINE, w=0.6):
        self.c.set_source_rgb(*colour)
        self.c.set_line_width(w)
        self.c.move_to(self.M, y)
        self.c.line_to(self.W - self.M, y)
        self.c.stroke()

    def need(self, h, header=None):
        if self.y + h > self.H - self.M - 14:
            self.footer()
            self.c.show_page()
            self.page += 1
            self.y = self.M
            if header:
                header()

    def footer(self):
        self.text(self.M, self.H - 24, "AliExpress Reader", 7, colour=MUTE)
        self.text(self.W - self.M, self.H - 24, f"page {self.page}", 7, colour=MUTE, right=True)

    def finish(self):
        self.footer()
        self.s.finish()


def summary_pdf(res, fh):
    """Write a printable summary of the orders to fh (a binary file)."""
    os_ = res["orders"]
    d = Doc(fh, f"AliExpress orders – {res['file']}")
    total = sum(spent(o) for o in os_)
    dates = sorted(o["date"] for o in os_ if o["date"])
    cur = os_[0]["currency"] if os_ else ""
    c, M, W = d.c, d.M, d.W
    # title band
    c.set_source_rgb(*ACCENT)
    c.rectangle(0, 0, W, 8)
    c.fill()
    d.text(M, 52, "AliExpress orders", 22, True)
    d.text(M, 70, f"From {res['file']} · read {datetime.now():%d %b %Y}", 9, colour=MUTE)
    # tiles
    tiles = [("Orders", str(len(os_))), (f"Total spent ({cur})", money(total)),
             ("First order", dates[0] if dates else "—"), ("Last order", dates[-1] if dates else "—"),
             ("Items not named", str(sum("itemsnotlisted" in o["flags"] for o in os_)))]
    tw = (W - 2 * M - 4 * 8) / 5
    for k, (label, val) in enumerate(tiles):
        x = M + k * (tw + 8)
        c.set_source_rgb(0.97, 0.96, 0.95)
        c.rectangle(x, 86, tw, 46)
        c.fill()
        d.text(x + 8, 101, label, 7.5, colour=MUTE)
        d.text(x + 8, 122, val, 14 if len(val) < 11 else 11, True)
    d.y = 156
    # by month
    months = _months(res)
    if months:
        d.text(M, d.y, "By month", 11, True)
        d.y += 14
        biggest = max(t for _, t in months.values()) or 1
        for k, (n, t) in months.items():
            d.need(14)
            d.text(M, d.y + 9, k, 8.5)
            c.set_source_rgb(*ACCENT)
            c.rectangle(M + 60, d.y + 1, (W - 2 * M - 190) * t / biggest, 10)
            c.fill()
            d.text(W - M - 70, d.y + 9, f"{n} order{'s' if n != 1 else ''}", 8, colour=MUTE)
            d.text(W - M, d.y + 9, money(t), 8.5, True, right=True)
            d.y += 14
        d.y += 12
    # order table
    cols = [("Date", M, 52), ("Order no.", M + 54, 86), ("Store", M + 142, 110), ("Items", M + 254, 170)]
    rx = W - M

    def header():
        d.text(M, d.y + 9, "Orders", 11, True) if d.page == 1 else None
        d.y += 16 if d.page == 1 else 0
        for name, x, _ in cols:
            d.text(x, d.y + 8, name, 7.5, True, MUTE)
        d.text(rx - 48, d.y + 8, "Extra", 7.5, True, MUTE, right=True)
        d.text(rx, d.y + 8, "Total", 7.5, True, MUTE, right=True)
        d.y += 12
        d.rule(d.y)
        d.y += 4

    d.need(60)
    header()
    for o in os_:
        item_lines = []
        for i in o["items"]:
            t = f"{i['qty']} × {money(i['unitPrice'])}  {i['title']}" + (f" ({i['variant']})" if i["variant"] else "")
            item_lines += d.wrap(t, cols[3][2], 7.5)
        if not o["items"]:
            item_lines = ["(not named on the Orders page)"]
        store = d.wrap(o["store"], cols[2][2], 8)
        notes = [n for n in o["notes"] if not any(w in n for w in ("cut short", "not named", "more than the items"))]
        h = max(len(item_lines) * 10, len(store) * 10, 20) + len(notes) * 10 + 6
        d.need(h, header)
        y0 = d.y + 9
        d.text(M, y0, o["date"], 8)
        d.text(M, y0 + 10, o["status"], 6.5, colour=MUTE)
        d.text(cols[1][1], y0, o["ref"], 7.5)
        for k, s in enumerate(store):
            d.text(cols[2][1], y0 + 10 * k, s, 8)
        for k, s in enumerate(item_lines):
            d.text(cols[3][1], y0 + 10 * k, s, 7.5, colour=WARN if not o["items"] else MUTE)
        for k, s in enumerate(notes):
            d.text(cols[3][1], y0 + 10 * (len(item_lines) + k), "⚠ " + s, 7, colour=WARN, width=W - M - cols[3][1])
        d.text(rx - 48, y0, money(o["extra"]) if o["extra"] is not None else "", 8, colour=MUTE, right=True)
        gone = "cancelled" in o["flags"]
        d.text(rx, y0, money(o["total"]), 8.5, not gone, MUTE if gone else INK, right=True)
        if gone:
            w_ = c.text_extents(money(o["total"])).x_advance
            c.set_source_rgb(*MUTE); c.set_line_width(0.6); c.move_to(rx - w_, y0 - 3); c.line_to(rx, y0 - 3); c.stroke()
        d.y += h
        d.rule(d.y - 3)
    d.need(30)
    d.y += 6
    d.text(cols[3][1], d.y + 8, f"{len(os_)} orders", 9, True)
    d.text(rx, d.y + 8, money(total), 11, True, ACCENT, right=True)
    d.y += 26
    d.need(30)
    for s in d.wrap("Extra = order total minus the items shown: shipping, GST and fees (minus = a discount). Orders with several items "
                    "don't name them on AliExpress's Orders page; their totals are still right.", W - 2 * M, 7):
        d.text(M, d.y, s, 7, colour=MUTE)
        d.y += 9
    d.finish()
