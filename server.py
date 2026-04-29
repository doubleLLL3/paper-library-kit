#!/usr/bin/env python3
"""
Paper Library local server: GET/PUT papers.json + static file hosting
Usage: python3 server.py [port]  (default: 8765)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    import fitz as _fitz
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _gen_thumb(pdf_path: str, thumb_path: str) -> bool:
    """Generate a PNG thumbnail of page 1. Returns True on success."""
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    if _HAS_FITZ:
        try:
            doc = _fitz.open(pdf_path)
            pix = doc[0].get_pixmap(matrix=_fitz.Matrix(150 / 72, 150 / 72))
            pix.save(thumb_path)
            doc.close()
            return True
        except Exception:
            pass
    for cmd in ["/opt/homebrew/bin/pdftoppm", "pdftoppm"]:
        if os.path.isfile(cmd) or shutil.which(cmd):
            prefix = thumb_path.removesuffix("-01.png")
            try:
                subprocess.run(
                    [cmd, "-f", "1", "-l", "1", "-r", "150", "-png", pdf_path, prefix],
                    check=True, capture_output=True,
                )
                matches = sorted(glob.glob(f"{prefix}-*.png"))
                if matches:
                    if matches[0] != thumb_path:
                        os.rename(matches[0], thumb_path)
                    return True
            except (subprocess.CalledProcessError, OSError):
                pass
            break
    return False
DATA_FILE = os.path.join(BASE_DIR, "papers.json")
BACKUP_DIR = os.path.join(BASE_DIR, ".backup")
os.makedirs(BACKUP_DIR, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/api/papers":
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            mtime = os.path.getmtime(DATA_FILE)
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "X-Mtime")
            self.send_header("X-Mtime", f"{mtime:.6f}")
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_PUT(self):
        if self.path == "/api/papers":
            try:
                payload = self._read_json_body()
                if "categories" not in payload or "papers" not in payload:
                    return self._send_json({"error": "missing keys"}, 400)

                # Optimistic concurrency: reject stale writes
                client_mtime = self.headers.get("X-If-Mtime")
                current_mtime = os.path.getmtime(DATA_FILE)
                if client_mtime is not None:
                    try:
                        if float(client_mtime) + 0.001 < current_mtime:
                            return self._send_json({
                                "error": "stale",
                                "message": "File was modified by another client. Please refresh and retry.",
                                "server_mtime": current_mtime,
                                "client_mtime": float(client_mtime),
                            }, 409)
                    except ValueError:
                        pass

                # Backup before overwrite
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, f"papers_{ts}.json"))

                with open(DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

                new_mtime = os.path.getmtime(DATA_FILE)
                data = json.dumps({"ok": True, "count": len(payload["papers"]), "mtime": new_mtime}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Expose-Headers", "X-Mtime")
                self.send_header("X-Mtime", f"{new_mtime:.6f}")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        self.send_response(405)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/upload":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not length:
                    return self._send_json({"error": "empty body"}, 400)
                raw_name = self.headers.get("X-Filename", "upload.pdf")
                filename = os.path.basename(urllib.parse.unquote(raw_name))
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"
                pdf_path = os.path.join(BASE_DIR, "references", filename)
                with open(pdf_path, "wb") as f:
                    f.write(self.rfile.read(length))
                thumb_name = filename[:-4] + "-01.png"
                thumb_path = os.path.join(BASE_DIR, "references", "thumbs", thumb_name)
                thumb_ok = _gen_thumb(pdf_path, thumb_path)
                self._send_json({"ok": True, "pdf": filename, "thumb": thumb_name if thumb_ok else None})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        if self.path == "/api/arxiv":
            try:
                body = self._read_json_body()
                raw = body.get("id", "").strip()
                m = re.search(r'\b(\d{4}\.\d{4,5}(?:v\d+)?)\b', raw)
                if not m:
                    return self._send_json({"error": "no arXiv ID found"}, 400)
                arxiv_id = m.group(1).split("v")[0]  # strip version suffix

                # Fetch metadata from arXiv Atom API
                meta_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
                with urllib.request.urlopen(meta_url, timeout=15) as resp:
                    xml_bytes = resp.read()
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "arxiv": "http://arxiv.org/schemas/atom",
                }
                root = ET.fromstring(xml_bytes)
                entry = root.find("atom:entry", ns)
                if entry is None:
                    return self._send_json({"error": "arXiv ID not found"}, 404)
                title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                authors = [
                    a.findtext("atom:name", "", ns).strip()
                    for a in entry.findall("atom:author", ns)
                ]
                published = entry.findtext("atom:published", "", ns)
                year = published[:4] if published else ""

                # Download PDF
                pdf_filename = f"{arxiv_id}.pdf"
                pdf_path = os.path.join(BASE_DIR, "references", pdf_filename)
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                req = urllib.request.Request(pdf_url, headers={"User-Agent": "paper-library/1.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    pdf_bytes = resp.read()
                os.makedirs(os.path.join(BASE_DIR, "references"), exist_ok=True)
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                # Generate thumbnail
                thumb_name = f"{arxiv_id}-01.png"
                thumb_path = os.path.join(BASE_DIR, "references", "thumbs", thumb_name)
                thumb_ok = _gen_thumb(pdf_path, thumb_path)

                self._send_json({
                    "ok": True,
                    "arxiv": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "pdf": pdf_filename,
                    "thumb": thumb_name if thumb_ok else None,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        self.send_response(405)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-If-Mtime, X-Filename")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Paper Library server: http://localhost:{port}")
    print(f"Data file: {DATA_FILE}")
    print(f"Backup dir: {BACKUP_DIR}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
