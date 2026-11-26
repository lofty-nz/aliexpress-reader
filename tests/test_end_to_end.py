"""Made-up Orders PDF (tests/make_sample.py) → reader → CSV / PDF summary / export. Needs poppler + pycairo."""
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import make_sample  # noqa: E402
import reader  # noqa: E402
import summary  # noqa: E402


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls.tmp.name) / "sample.pdf"
        make_sample.draw(str(cls.pdf))
        cls.res = reader.read_pdf(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_order_read(self):
        os_ = self.res["orders"]
        self.assertEqual([o["ref"] for o in os_], [r[1] for r in make_sample.ORDERS])
        for o, (_, _, status, store, total, items) in zip(os_, make_sample.ORDERS):
            self.assertEqual((o["status"], o["store"], o["total"]), (status, store, round(float(total) * 100)))
            self.assertEqual(len(o["items"]), len(items))
        self.assertEqual(self.res["pages"], 2)
        self.assertNotIn("Returns/refunds", json.dumps([{k: v for k, v in o.items() if k != "notes"} for o in os_]))

    def test_cancelled_not_spent(self):
        gone = [o for o in self.res["orders"] if o["status"] == "Cancelled"][0]
        self.assertIn("cancelled", gone["flags"])
        self.assertEqual(reader.spent(gone), 0)
        want = sum(round(float(r[4]) * 100) for r in make_sample.ORDERS if r[2] != "Cancelled")
        self.assertEqual(sum(reader.spent(o) for o in self.res["orders"]), want)
        ld = reader.list_doc(self.res)
        self.assertEqual(ld["facts"]["total"], want)
        line = [ln for ln in ld["lines"] if ln["ref"] == gone["ref"]][0]
        self.assertEqual((line["amount"], line["kind"]), (None, "cancelled"))

    def test_csv(self):
        rows = list(csv.reader(io.StringIO(summary.orders_csv(self.res).lstrip("﻿"))))
        self.assertEqual(rows[0][0], "date")
        self.assertEqual(len([r for r in rows[1:] if r and r[0]]), len(make_sample.ORDERS))
        want = sum(reader.spent(o) for o in self.res["orders"])
        self.assertEqual(rows[-1][7], f"{want / 100:.2f}")

    def test_pdf_summary(self):
        buf = io.BytesIO()
        summary.summary_pdf(self.res, buf)
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))
        out = Path(self.tmp.name) / "summary.pdf"
        out.write_bytes(buf.getvalue())
        text = subprocess.run(["pdftotext", str(out), "-"], capture_output=True, text=True).stdout
        self.assertIn("AliExpress orders", text)
        self.assertIn("Kowhai Maker Supplies Store", text)
        want = sum(reader.spent(o) for o in self.res["orders"])
        self.assertIn(f"${want / 100:,.2f}", text)

    def test_export(self):
        with tempfile.TemporaryDirectory() as t:
            r = reader.export(self.res, t)
            self.assertEqual(r["count"], len(make_sample.ORDERS))
            self.assertTrue((Path(t) / "AliExpress order 9001000000000101.json").exists())


if __name__ == "__main__":
    unittest.main()
