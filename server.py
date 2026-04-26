#!/usr/bin/env python3
"""
Paper Library local server: GET/PUT papers.json + static file hosting
Usage: python3 server.py [port]  (default: 8765)
"""
import json
import os
import sys
import shutil
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-If-Mtime")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Paper Library server: http://localhost:{port}")
    print(f"Data file: {DATA_FILE}")
    print(f"Backup dir: {BACKUP_DIR}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
