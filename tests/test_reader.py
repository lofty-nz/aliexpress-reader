"""Reader tests on MADE-UP orders laid out like a printed AliExpress Orders page (no real order data here).
Run: python3 -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reader  # noqa: E402


def L(page, x, y, text):
    return {"page": page, "x0": x, "y0": y, "x1": x + 6 * len(text), "y1": y + 9, "y": (page - 1) * reader.PAGE_GAP + y, "text": text}


def order(page, y, date, ref, store, total, items=(), indent=0, status="Completed"):
    out = [L(page, 441, y, f"Date: {date}"), L(page, 377, y + 10, f"Ref. Number: {ref} Copy"), L(page, 140, y + 4, status),
           L(page, 511, y + 4, "Details"), L(page, 140 + indent, y + 30, store), L(page, 447, y + 46, f"Total:NZ$ {total}"),
           L(page, 457, y + 84, "Add to cart"), L(page, 462, y + 105, "Remove")]
    yy = y + 46
    for title, variant, price in items:
        out.append(L(page, 206, yy, title)); yy += 16
        if variant:
            out.append(L(page, 206, yy, variant)); yy += 16
        out.append(L(page, 206, yy, price)); yy += 14
        out.append(L(page, 206, yy, "NZ$2 coupon if delayed")); yy += 9
        out.append(L(page, 206, yy, "Free returns")); yy += 9
    return out


SIDEBAR = [L(1, 44, 120, "Overview"), L(1, 44, 160, "Payment"), L(1, 44, 302, "Help center"), L(1, 44, 372, "Penalties informati…"),
           L(1, 39, 452, "Search Anywhere, Anytime!"), L(1, 140, 98, "View all"), L(1, 332, 98, "Completed")]


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.lines = SIDEBAR + \
            order(1, 155, "Oct 28, 2026", "1111222233334444", "Kea Parts Store", "60.00",
                  [("Made-up Widget 3.3V Board …", "With Case", "NZ$ 12.50 x4")]) + \
            order(1, 297, "Oct 21, 2026", "1111222233335555", "Tui Bits Store", "24.10", [], indent=29) + \
            order(1, 440, "Sep 8, 2026", "1111222233336666", "Weka Wholesale Store", "1,204.30",
                  [("Big Made-up Thing", "", "NZ$ 0.58 x50")]) + \
            order(2, 40, "Jul 24, 2026", "1111222233337777", "Moa Official Store", "9.00",
                  [("Small Made-up Part", "Red", "NZ$ 10.00 x1")], status="Awaiting delivery")

    def test_orders(self):
        os = reader.read_lines(self.lines)
        self.assertEqual([o["ref"] for o in os], ["1111222233334444", "1111222233335555", "1111222233336666", "1111222233337777"])
        a, b, c, d = os
        self.assertEqual((a["date"], a["status"], a["store"], a["total"], a["currency"]), ("2026-10-28", "Completed", "Kea Parts Store", 6000, "NZ$"))
        self.assertEqual(len(a["items"]), 1)
        i = a["items"][0]
        self.assertEqual((i["title"], i["variant"], i["unitPrice"], i["qty"], i["amount"]), ("Made-up Widget 3.3V Board …", "With Case", 1250, 4, 5000))
        self.assertEqual(i["tags"], ["NZ$2 coupon if delayed", "Free returns"])
        self.assertTrue(i["truncated"])
        self.assertEqual(a["extra"], 1000)

    def test_side_menu_and_buttons_kept_out(self):
        text = json.dumps([{k: v for k, v in o.items() if k != "notes"} for o in reader.read_lines(self.lines)])
        for word in ("Help center", "Penalties", "Search Anywhere", "Add to cart", "Remove", "Details"):
            self.assertNotIn(word, text)

    def test_items_not_named(self):
        b = reader.read_lines(self.lines)[1]
        self.assertEqual((b["store"], b["items"], b["itemsTotal"], b["total"]), ("Tui Bits Store", [], None, 2410))
        self.assertIn("itemsnotlisted", b["flags"])

    def test_thousands_and_qty(self):
        c = reader.read_lines(self.lines)[2]
        self.assertEqual(c["total"], 120430)
        self.assertEqual(c["items"][0]["amount"], 2900)
        self.assertEqual(c["items"][0]["variant"], "")

    def test_discount_and_status_and_page2(self):
        d = reader.read_lines(self.lines)[3]
        self.assertEqual((d["status"], d["page"], d["extra"]), ("Awaiting delivery", 2, -100))
        self.assertTrue(any("less than the items" in n for n in d["notes"]))

    def test_export_shapes(self):
        res = {"file": "made-up.pdf", "pages": 2, "orders": reader.read_lines(self.lines), "warnings": []}
        with tempfile.TemporaryDirectory() as t:
            reader.export(res, t)
            names = sorted(p.name for p in Path(t).iterdir())
            self.assertIn("all-transactions.csv", names)
            self.assertIn("documents.csv", names)
            self.assertIn("items.csv", names)
            lst = json.loads((Path(t) / "AliExpress orders - made-up.json").read_text())
            self.assertEqual([ln["amount"] for ln in lst["lines"]], [-6000, -2410, -120430, -900])
            self.assertEqual(lst["lines"][0]["kind"], "txn")
            inv = json.loads((Path(t) / "AliExpress order 1111222233334444.json").read_text())
            self.assertEqual(inv["docType"], "invoice")
            self.assertEqual(inv["facts"]["invoiceNo"], "1111222233334444")
            self.assertEqual(inv["facts"]["total"], 6000)
            self.assertEqual(sum(ln["amount"] for ln in inv["lines"]), 6000)     # items + worked-out extra add up
            self.assertTrue(inv["check"]["ok"])


    def test_unknown_status_refund_and_suggestions_grid(self):
        lines = SIDEBAR + [L(1, 44, 175, "Returns/refunds")] + \
            order(1, 155, "Apr 28, 2026", "2222333344445555", "Hoiho Store", "8.02",
                  [("Made-up Cable …", "Black 0.5m", "NZ$ 6.98 x1")], status="Awaiting pickup") + \
            [L(1, 206, 260, "Collect NZ$2 for delivery issue"), L(1, 154, 280, "Refund complete")] + \
            order(1, 320, "Apr 20, 2026", "2222333344446666", "Takahe Store", "5.00",
                  [("Made-up Fuse", "", "NZ$ 5.00 x1")], status="Expired") + \
            [L(1, 140, 520, "More to love"), L(1, 206, 540, "Made-up Gadget"), L(1, 206, 556, "NZ$ 12.99"), L(1, 206, 570, "1K+ sold"),
             L(1, 206, 600, "2026 AliExpress.com. All rights reserved.")]
        a, b = reader.read_lines(lines)
        self.assertEqual(a["status"], "Awaiting pickup")                       # unknown status found by position
        self.assertIn("Collect NZ$2 for delivery issue", a["items"][0]["tags"])
        self.assertEqual(a["refund"], "Refund complete")
        self.assertIn("refund", a["flags"])
        self.assertEqual((b["status"], reader.spent(b)), ("Expired", 0))
        self.assertEqual(len(b["items"]), 1)                                   # suggestions grid not added to the last order
        self.assertFalse(any("without a price" in n for n in b["notes"]))


if __name__ == "__main__":
    unittest.main()
