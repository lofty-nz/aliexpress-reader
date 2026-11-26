// node tests/web_read.mjs file.pdf -> {res, xeroCsv, xeroJson, ordersCsv} from the WEBSITE version (web/*.mjs + bundled pdf.js)
import fs from "fs";
import path from "path";
import {fileURLToPath, pathToFileURL} from "url";
const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "web");
const pdfjs = await import(pathToFileURL(path.join(web, "vendor/pdf.min.mjs")).href);
pdfjs.GlobalWorkerOptions.workerSrc = pathToFileURL(path.join(web, "vendor/pdf.worker.min.mjs")).href;
const R = await import(pathToFileURL(path.join(web, "reader.mjs")).href);
const X = await import(pathToFileURL(path.join(web, "xero.mjs")).href);
const doc = await pdfjs.getDocument({data: new Uint8Array(fs.readFileSync(process.argv[2])), verbosity: 0, useSystemFonts: false}).promise;
const res = await R.readPdf(doc, path.basename(process.argv[2]));
const opts = JSON.parse(process.argv[3] || "{}");
console.log(JSON.stringify({res, ordersCsv: R.ordersCsv(res), xeroCsv: X.xeroCsv(res, opts), xeroJson: X.xeroJson(res, opts)}));
