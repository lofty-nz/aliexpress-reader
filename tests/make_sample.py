"""Draw a MADE-UP printed Orders page PDF (same layout as the browser printout: side menu, status column, items,
Total/buttons column, 2 pages, one multi-item order with no item names). For end-to-end tests and screenshots.

    python3 tests/make_sample.py out.pdf
"""
import sys

import cairo

ORDERS = [  # date, ref, status, store, total, [(title, option, "price xqty")]
    ("Nov 18, 2026", "9001000000000101", "Awaiting delivery", "Kowhai Maker Supplies Store", "86.40",
     [("ESP32-C6 Dev Board 1.47inch LCD Touch Screen with Case …", "With Touch LCD", "NZ$ 24.80 x3")]),
    ("Nov 9, 2026", "9001000000000102", "Completed", "Tui Tools Official Store", "47.15",
     [("Mini Soldering Iron 65W USB-C Smart Temperature Control …", "Black, TS-B2 tip", "NZ$ 41.02 x1")]),
    ("Oct 30, 2026", "9001000000000103", "Completed", "Weka Electronics Store", "12.66",
     [("100pcs 1N5408 Rectifier Diode 3A 1000V DO-201AD Axial …", "100pcs", "NZ$ 9.34 x1")]),
    ("Oct 30, 2026", "9001000000000104", "Completed", "Pukeko Parts Direct Store", "63.90", []),
    ("Oct 12, 2026", "9001000000000105", "Completed", "Kea Precision Store", "38.27",
     [("JST-XH 2.54mm Connector Kit 2/3/4/5/6 Pin Pre-Crimped Wire …", "XH 2.54, 300pcs", "NZ$ 15.12 x2")]),
    ("Sep 21, 2026", "9001000000000106", "Completed", "Ruru Module Store", "54.18",
     [("DS3231 Precision RTC Module I2C Real Time Clock for Arduino …", "", "NZ$ 1.06 x40")]),
    ("Sep 2, 2026", "9001000000000107", "Completed", "Moa Display Official Store", "131.73",
     [("1.75inch AMOLED Round Touch Display ESP32-S3 Development …", "ESP32-S3 1.75 AMOLED", "NZ$ 56.11 x2")]),
    ("Aug 15, 2026", "9001000000000108", "Cancelled", "Hihi Cable Store", "18.40",
     [("Silicone Wire 20AWG Soft Flexible Tinned Copper 10m …", "Red + Black", "NZ$ 8.70 x2")]),
]
MENU = ["Account", "Overview", "Orders", "Payment", "Returns/refunds", "Feedback", "Settings", "Shipping address", "Message center"]


def draw(path):
    W, H = 595.276, 841.89
    s = cairo.PDFSurface(path, W, H)
    c = cairo.Context(s)

    def t(x, y, text, size=7.5, bold=False, rgb=(0.1, 0.1, 0.1)):
        c.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        c.set_font_size(size)
        c.set_source_rgb(*rgb)
        c.move_to(x, y)
        c.show_text(text)

    def btn(x, y, label):
        c.set_source_rgb(0.75, 0.75, 0.75)
        c.set_line_width(0.6)
        c.rectangle(x - 30, y - 9, 112, 14)
        c.stroke()
        t(x, y, label, 6.5, True)

    y = 90
    page = 1
    t(44, 80, "Home > Account > Orders", 6.5)
    for k, m in enumerate(MENU):
        t(44, 110 + 18 * k, m, 7.5, k == 0)
    for date, ref, status, store, total, items in ORDERS:
        h = 60 + max(1, len(items)) * 50
        if y + h > H - 40:
            c.show_page()
            page += 1
            y = 40
        t(442, y + 8, f"Date: {date}", 6)
        t(377, y + 18, f"Ref. Number: {ref} Copy", 6)
        t(140, y + 12, status, 8, True)
        t(512, y + 12, "Details", 6.5, True)
        t(140, y + 38, store, 7)
        t(447, y + 58, f"Total:NZ$ {total}", 7.5, True)
        btn(452, y + 72, "Write a review")
        btn(457, y + 92, "Add to cart")
        btn(462, y + 112, "Remove")
        yy = y + 58
        for title, option, price in items:
            t(206, yy, title, 7)
            yy += 16
            if option:
                t(206, yy, option, 7)
                yy += 16
            t(206, yy, price, 7)
            yy += 14
            t(206, yy, "Free returns", 5.5, rgb=(0.1, 0.6, 0.4))
            yy += 10
        y += h + 20
    s.finish()


if __name__ == "__main__":
    draw(sys.argv[1] if len(sys.argv) > 1 else "sample-orders.pdf")
