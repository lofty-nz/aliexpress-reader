"""Xero export + the website version (web/*.mjs) gives the same answers as the Python one. Made-up PDF only.
The web part needs node; skipped without it."""
import csv
import io
import json
import shutil
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
import xero  # noqa: E402

KEYS = ["ref", "date", "status", "store", "currency", "total", "itemsTotal", "extra", "page", "pages", "flags", "notes", "refund", "box"]


class XeroAndWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls.tmp.name) / "sample.pdf"
        make_sample.draw(str(cls.pdf))
        cls.res = reader.read_pdf(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_csv_bills_add_up_and_skip_cancelled(self):
        rows = list(csv.DictReader(io.StringIO(xero.xero_csv(self.res))))
        self.assertEqual(list(rows[0])[:2], ["*ContactName", "EmailAddress"])
        paid = [o for o in self.res["orders"] if "cancelled" not in o["flags"]]
        self.assertEqual({r["*InvoiceNumber"] for r in rows}, {o["ref"] for o in paid})
        for o in paid:
            lines = [r for r in rows if r["*InvoiceNumber"] == o["ref"]]
            got = sum(round(float(r["*Quantity"]) * float(r["*UnitAmount"]) * 100) for r in lines)
            self.assertEqual(got, o["total"], o["ref"])
        r = rows[0]
        self.assertEqual((r["*ContactName"], r["*InvoiceDate"], r["*DueDate"], r["*AccountCode"], r["*TaxType"], r["Currency"]),
                         ("AliExpress", "18/11/2026", "18/11/2026", "300", "No GST", "NZD"))
        self.assertTrue(any("not named" in r["Description"] for r in rows))          # the multi-item order: one line for its total

    def test_api_json(self):
        body = json.loads(xero.xero_json(self.res, {"tax": "gst", "account": "429", "contact": "Ali"}))
        b = body["Invoices"][0]
        self.assertEqual((b["Type"], b["Status"], b["LineAmountTypes"], b["Contact"]["Name"], b["CurrencyCode"]), ("ACCPAY", "DRAFT", "Inclusive", "Ali", "NZD"))
        self.assertEqual({li["TaxType"] for li in b["LineItems"]}, {"INPUT2"})
        self.assertEqual(round(sum(li["Quantity"] * li["UnitAmount"] for li in b["LineItems"]), 2), 86.40)
        self.assertNotIn("9001000000000108", [x["InvoiceNumber"] for x in body["Invoices"]])     # cancelled

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_website_version_same_answers(self):
        for opts in ({}, {"tax": "gst", "account": "429"}):
            out = subprocess.run(["node", str(HERE / "web_read.mjs"), str(self.pdf), json.dumps(opts)], capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, out.stderr[-500:])
            web = json.loads(out.stdout)
            self.assertEqual(len(web["res"]["orders"]), len(self.res["orders"]))
            for a, b in zip(self.res["orders"], web["res"]["orders"]):
                for k in KEYS:
                    if k == "box":
                        self.assertAlmostEqual(a["box"]["y0"], b["box"]["y0"], delta=3)
                        continue
                    self.assertEqual(a[k], b[k], (a["ref"], k))
                self.assertEqual([{k: i[k] for k in ("title", "variant", "unitPrice", "qty", "amount", "tags")} for i in a["items"]],
                                 [{k: i[k] for k in ("title", "variant", "unitPrice", "qty", "amount", "tags")} for i in b["items"]])
            self.assertEqual(web["xeroCsv"].replace("\r\n", "\n"), xero.xero_csv(self.res, opts).replace("\r\n", "\n"))
            self.assertEqual(json.loads(web["xeroJson"]), json.loads(xero.xero_json(self.res, opts)))
            self.assertEqual(web["ordersCsv"].replace("\r\n", "\n"), summary.orders_csv(self.res).replace("\r\n", "\n"))


if __name__ == "__main__":
    unittest.main()
