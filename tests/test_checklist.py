"""✅ Checklist (web/checklist.mjs, used by both versions): automatic groups, one row per item, CSV. Needs node."""
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

JS = """
const C = await import(process.argv[2]);
const res = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const names = JSON.parse(process.argv[4]);
const tags = {...C.emptyTags(), items: {[C.checklistRows(res)[0].key]: {done: true, job: "1234", staff: "Sam"},
                                        [C.checklistRows(res)[1].key]: {group: "Stock"}}};
console.log(JSON.stringify({groups: names.map(n => C.autoGroup(...n)), rows: C.checklistRows(res), csv: C.checklistCsv(res, tags)}));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class Checklist(unittest.TestCase):
    def run_js(self, names):
        with tempfile.TemporaryDirectory() as t:
            pdf = Path(t) / "s.pdf"
            make_sample.draw(str(pdf))
            res = reader.read_pdf(pdf)
            (Path(t) / "r.json").write_text(json.dumps(res))
            js = Path(t) / "t.cjs"
            js.write_text("(async () => {" + JS + "})()")
            out = subprocess.run(["node", str(js), str(HERE.parent / "web" / "checklist.mjs"), str(Path(t) / "r.json"), json.dumps(names)],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr[-400:])
            return res, json.loads(out.stdout)

    def test_groups(self):
        names = [["ESP32-C6 Dev Board 1.47inch LCD Touch Screen with Case …", "With Touch LCD"],
                 ["Luxury Flip Case For Samsung Galaxy A54", ""],
                 ["WT32-ETH01 Embedded Serial Port Networking Bluetooth", "Soldered"],      # option says "Soldered": still a board
                 ["9 Pcs Tweezers Set Stainless Steel Anti-Static", "Black"],
                 ["JST-XH 2.54mm Connector Socket Kit with Pre-Crimped", ""],
                 ["10PCS 5W Zener Diode DO-15", ""],
                 ["20/100Pcs Random Color Chicken Leg Rings", ""],
                 ["Step Down Power Supply Module Buck Converter", ""],
                 ["Vac Vacuum Cleaner Motor", ""],
                 ["Genuine Leather Ratchet Belt", ""]]
        _, out = self.run_js(names)
        self.assertEqual(out["groups"], ["Dev boards & displays", "Phone, computer & AV", "Dev boards & displays", "Tools & soldering",
                                         "Connectors & cables", "Components", "Chickens & pets", "Modules & power", "Appliance parts", "Other"])

    def test_rows_and_csv(self):
        res, out = self.run_js([])
        n_items = sum(len(o["items"]) or 1 for o in res["orders"])
        self.assertEqual(len(out["rows"]), n_items)
        self.assertEqual(len({r["key"] for r in out["rows"]}), n_items)                 # keys unique
        self.assertTrue(any(r["auto"] == "Not named (several items)" for r in out["rows"]))
        rows = list(csv.DictReader(io.StringIO(out["csv"].lstrip("﻿"))))
        self.assertEqual(len(rows), n_items)
        first = out["rows"][0]
        mine = [r for r in rows if r["order number"] == first["ref"] and r["item"] == first["title"]][0]
        self.assertEqual((mine["ticked"], mine["job number"], mine["staff"]), ("yes", "1234", "Sam"))
        self.assertEqual(sum(r["group"] == "Stock" for r in rows), 1)


if __name__ == "__main__":
    unittest.main()
