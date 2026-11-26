#!/usr/bin/env python3
"""AliExpress Reader web page — 127.0.0.1:8835 (localhost only). Stdlib only.

Open a printed AliExpress Orders PDF (pick from a folder or drop one on the page), see each order with its
spot on the page, then 💾 Export → ~/Documents/AliExpress Reader exports/<name> <date>/ (Statement Teacher shapes).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import reader

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("ALIEXPRESS_READER_DATA", str(HERE / "data")))
PORT = int(os.environ.get("ALIEXPRESS_READER_PORT", "8835"))
EXPORTS = Path(os.environ.get("ALIEXPRESS_READER_EXPORTS", str(Path.home() / "Documents" / "AliExpress Reader exports")))
DOCS = DATA / "docs"


def doc_id(raw):
    return hashlib.sha256(raw).hexdigest()[:16]


def doc_path(i):
    if not re.fullmatch(r"[0-9a-f]{16}", i or ""):
        raise ValueError("bad id")
    return DOCS / i


def add_pdf(raw, name):
    if not raw.startswith(b"%PDF"):
        return {"error": "That isn't a PDF."}
    i = doc_id(raw)
    d = doc_path(i)
    d.mkdir(parents=True, exist_ok=True)
    (d / "file.pdf").write_bytes(raw)
    meta = {"id": i, "name": name, "added": datetime.now().isoformat(timespec="seconds")}
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return read_doc(i)


def read_doc(i):
    d = doc_path(i)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    res = reader.read_pdf(d / "file.pdf")
    res["file"] = meta["name"]
    res["id"] = i
    (d / "read.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def docs():
    out = []
    for m in sorted(DOCS.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = json.loads(m.read_text(encoding="utf-8"))
        r = m.parent / "read.json"
        if r.exists():
            res = json.loads(r.read_text(encoding="utf-8"))
            meta.update(orders=len(res["orders"]), total=sum(o["total"] or 0 for o in res["orders"]))
        out.append(meta)
    return out


def page_png(i, page):
    d = doc_path(i)
    png = d / f"page-{int(page)}.png"
    if not png.exists():
        subprocess.run(["pdftoppm", "-r", "110", "-png", "-singlefile", "-f", str(int(page)), "-l", str(int(page)),
                        str(d / "file.pdf"), str(png)[:-4]], check=True)
    return png.read_bytes()


def folder_pdfs(folder):
    p = Path(folder).expanduser()
    if not p.is_dir():
        return {"error": f"No folder {p}"}
    return {"folder": str(p), "parent": str(p.parent),
            "dirs": sorted(x.name for x in p.iterdir() if x.is_dir() and not x.name.startswith(".")),
            "pdfs": sorted(x.name for x in p.iterdir() if x.suffix.lower() == ".pdf")}


def do_export(i):
    d = doc_path(i)
    res = json.loads((d / "read.json").read_text(encoding="utf-8"))
    folder = EXPORTS / reader._safe(f"{Path(res['file']).stem} {datetime.now():%Y-%m-%d %H%M}")
    return reader.export(res, folder)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/health":
                return self.send(200, {"ok": True, "version": reader.VERSION})
            if u.path == "/api/docs":
                return self.send(200, docs())
            if u.path == "/api/doc":
                r = doc_path(q.get("id")) / "read.json"
                return self.send(200, json.loads(r.read_text(encoding="utf-8")) if r.exists() else read_doc(q["id"]))
            if u.path == "/api/page":
                return self.send(200, page_png(q["id"], q.get("p", 1)), "image/png")
            if u.path == "/api/folder":
                return self.send(200, folder_pdfs(q.get("path") or str(Path.home() / "Sandbox")))
        except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/upload":
                return self.send(200, add_pdf(raw, parse_qs(u.query).get("name", ["upload.pdf"])[0]))
            b = json.loads(raw or b"{}")
            if u.path == "/api/open-path":
                p = Path(b["path"]).expanduser()
                return self.send(200, add_pdf(p.read_bytes(), p.name))
            if u.path == "/api/reread":
                return self.send(200, read_doc(b["id"]))
            if u.path == "/api/export":
                return self.send(200, do_export(b["id"]))
            if u.path == "/api/remove":
                shutil.rmtree(doc_path(b["id"]))
                return self.send(200, {"ok": True})
        except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    print(f"AliExpress Reader {reader.VERSION} on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
