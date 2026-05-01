#!/usr/bin/env python3
"""
Paper Library local server: GET/PUT papers.json + static file hosting
Usage: python3 server.py [port]  (default: 8765)
"""
import glob
import html as html_mod
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

# ── PDF metadata extraction ──────────────────────────────────────────────────

_INST_KW = re.compile(
    r'\b('
    # English generic
    r'university|universit[eéy]|institute|institution|college|school of|faculty|'
    r'department|dept\.?|division|center|centre|laboratory|laboratories|lab\b|'
    r'research|technology|national|international|'
    # Well-known US
    r'carnegie|mellon|stanford|berkeley|harvard|princeton|caltech|cornell|columbia|'
    r'yale|nyu|ucsd|uiuc|gatech|mit\b|'
    # Well-known non-US
    r'oxford|cambridge|imperial|ucl|edinburgh|eth\b|epfl|inria|mpi\b|max.?planck|'
    r'tsinghua|peking|fudan|zhejiang|sjtu|tongji|hkust|nus\b|ntu\b|kaist|kaust|'
    r'toronto|mcgill|waterloo|amsterdam|delft|lund|kth\b|aalto|rwth|'
    # Industry / AI labs
    r'deepmind|openai|anthropic|google|microsoft|meta\b|nvidia|apple|amazon|'
    r'physical intelligence|physical.intelligence|'
    r'corporation|corp\b|inc\b|ltd\b|gmbh'
    r')\b',
    re.I,
)

_DEPT_PAT = re.compile(
    r'\b(department|dept\.?|school|faculty|division|center|centre|lab|laboratory|'
    r'institute|college)\s+(of|for)\b',
    re.I,
)

_SUPERSCRIPT_CLEAN = re.compile(r'^[\d¹²³⁴⁵⁶⁷⁸⁹⁰,\s\*†‡§¶]+')
_LOCATION_SUFFIX = re.compile(
    r',\s*(USA|U\.S\.A\.|UK|U\.K\.|China|Japan|Germany|France|Canada|'
    r'Australia|Singapore|South Korea|Switzerland|Netherlands|Sweden|'
    r'Italy|Spain|Brazil|India|Israel|Denmark|Norway|Finland)\s*$',
    re.I,
)


def _extract_pdf_meta(pdf_path: str):
    """Return (title, arxiv_id, org) extracted from first-page text of pdf_path."""
    pdf_title = None
    pdf_arxiv = None
    pdf_org = None
    try:
        txt = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "2", pdf_path, "-"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]

        # ── Title block: collect up to 2 long lines before abstract/section markers ──
        title_parts = []
        stop_idx = min(15, len(lines))
        for i, line in enumerate(lines[:15]):
            if re.search(
                r'^(abstract|introduction|\d[\.\s]|©|arxiv:|submitted|preprint|accepted|keywords|email)',
                line.lower(),
            ):
                stop_idx = i
                break
            if len(line) > 12:
                title_parts.append(line)
            if len(title_parts) >= 2:
                stop_idx = i + 1
                break

        if title_parts:
            pdf_title = " ".join(title_parts)

        # ── arXiv ID ──
        arxiv_m = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5})', txt, re.I)
        if not arxiv_m:
            arxiv_m = re.search(r'\b(\d{4}\.\d{4,5})\b', txt)
        if arxiv_m:
            pdf_arxiv = arxiv_m.group(1)

        # ── Org: search lines after title block (up to 25 lines) ──
        search_lines = lines[stop_idx: stop_idx + 25]

        candidates = []
        for line in search_lines:
            # Skip very short, very long, URLs, or obvious non-affiliation lines
            if len(line) < 5 or len(line) > 200:
                continue
            if re.search(r'^https?://', line):
                continue
            if re.search(r'^(abstract|keywords|email|correspondence|equal\s+contribution)', line.lower()):
                break

            cleaned = _SUPERSCRIPT_CLEAN.sub('', line).strip(' ,;*†‡§¶')
            if not cleaned or re.search(r'^https?://', cleaned):
                continue

            score = 0
            if _DEPT_PAT.search(cleaned):
                score += 3       # "Department of X" is very reliable
            if _INST_KW.search(cleaned):
                score += 2
            if _LOCATION_SUFFIX.search(cleaned):
                score += 1       # ends with a country name
            # Lines with @ are emails — don't use the raw line as org
            if '@' in cleaned:
                continue

            if score > 0:
                candidates.append((score, cleaned))

        if candidates:
            # Pick highest-scoring; prefer shorter lines when tied (avoid multi-author lines)
            candidates.sort(key=lambda x: (-x[0], len(x[1])))
            best = candidates[0][1]
            # If line lists multiple institutions (e.g. "Inst A, 2 Inst B" or "Inst A 2 Inst B"), keep only the first
            first_inst = re.split(r'(?:,\s*|\s+)\d+\s+[A-Z]', best)[0].strip(' ,')
            pdf_org = first_inst if first_inst else best

        # Fallback: academic email domain → institution hint
        if not pdf_org:
            for em in re.finditer(r'@([\w\-\.]+\.(edu|ac\.\w{2,}))', txt, re.I):
                domain = em.group(1).lower()
                if 'github' not in domain and 'arxiv' not in domain:
                    parts = domain.split('.')
                    pdf_org = '.'.join(parts[-3:]) if len(parts) >= 3 else domain
                    break

    except Exception:
        pass
    return pdf_title, pdf_arxiv, pdf_org


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
                # arXiv ID from filename
                pdf_arxiv = None
                stem_name = os.path.splitext(filename)[0]
                m = re.search(r'\b(\d{4}\.\d{4,5})\b', stem_name)
                if m:
                    pdf_arxiv = m.group(1)
                # Title from pdfinfo metadata (highest quality)
                pdf_title = None
                try:
                    info_out = subprocess.run(
                        ["pdfinfo", pdf_path], capture_output=True, text=True, timeout=10
                    ).stdout
                    for line in info_out.split("\n"):
                        if line.lower().startswith("title:"):
                            t = line[6:].strip()
                            if t and t.lower() not in ("untitled", "unknown", ""):
                                pdf_title = t
                            break
                except Exception:
                    pass
                # Title, arXiv ID, org from first-page text
                txt_title, txt_arxiv, pdf_org = _extract_pdf_meta(pdf_path)
                if not pdf_title:
                    pdf_title = txt_title
                if not pdf_arxiv:
                    pdf_arxiv = txt_arxiv
                self._send_json({"ok": True, "pdf": filename, "thumb": thumb_name if thumb_ok else None,
                                 "title": pdf_title, "arxiv": pdf_arxiv, "org": pdf_org})
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
                # Affiliation from API (rarely populated; we'll also extract from PDF below)
                api_org = None
                for author in entry.findall("atom:author", ns):
                    aff = author.findtext("arxiv:affiliation", "", ns).strip()
                    if aff:
                        api_org = aff
                        break

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

                # Extract org from PDF text (more reliable than API affiliation field)
                _, _, pdf_org = _extract_pdf_meta(pdf_path)
                org = api_org or pdf_org

                self._send_json({
                    "ok": True,
                    "arxiv": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "org": org,
                    "pdf": pdf_filename,
                    "thumb": thumb_name if thumb_ok else None,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        if self.path == "/api/fetch-og":
            try:
                body = self._read_json_body()
                url = body.get("url", "").strip()
                if not url:
                    return self._send_json({"error": "no url"}, 400)
                if not url.startswith("http"):
                    url = "https://" + url
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; paper-library/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html_bytes = resp.read(512 * 1024)
                html_text = html_bytes.decode("utf-8", errors="replace")
                # Find og:image or twitter:image
                img_url = None
                for pat in [
                    r'property=["\']og:image["\'][^>]*content=["\'](https?://[^"\'>\s]+)',
                    r'content=["\'](https?://[^"\'>\s]+)["\'][^>]*property=["\']og:image["\']',
                    r'name=["\']twitter:image["\'][^>]*content=["\'](https?://[^"\'>\s]+)',
                    r'content=["\'](https?://[^"\'>\s]+)["\'][^>]*name=["\']twitter:image["\']',
                ]:
                    m = re.search(pat, html_text, re.I)
                    if m:
                        img_url = m.group(1)
                        break
                # Extract og:title and og:site_name regardless of image
                og_title = None
                og_site = None
                for key, pats in [
                    ("title", [r'property=["\']og:title["\'][^>]*content=["\'](.*?)["\']',
                               r'content=["\'](.*?)["\'][^>]*property=["\']og:title["\']']),
                    ("site",  [r'property=["\']og:site_name["\'][^>]*content=["\'](.*?)["\']',
                               r'content=["\'](.*?)["\'][^>]*property=["\']og:site_name["\']']),
                ]:
                    for pat in pats:
                        mm = re.search(pat, html_text, re.I)
                        if mm:
                            val = html_mod.unescape(mm.group(1).strip())
                            if key == "title":
                                og_title = val
                            else:
                                og_site = val
                            break

                if not img_url:
                    return self._send_json({"ok": False, "error": "页面中未找到 og:image",
                                            "title": og_title, "org": og_site})
                img_req = urllib.request.Request(
                    img_url, headers={"User-Agent": "Mozilla/5.0 (compatible; paper-library/1.0)"}
                )
                with urllib.request.urlopen(img_req, timeout=15) as resp:
                    img_bytes = resp.read(10 * 1024 * 1024)
                    content_type = resp.headers.get("content-type", "")
                ext = ".jpg" if "jpeg" in content_type or "jpg" in content_type else ".webp" if "webp" in content_type else ".png"
                parsed_host = re.sub(r'[^a-zA-Z0-9]', '_', urllib.parse.urlparse(url).netloc.replace("www.", ""))[:24]
                thumb_name = f"{parsed_host}_og{ext}"
                thumb_path = os.path.join(BASE_DIR, "references", "thumbs", thumb_name)
                os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                with open(thumb_path, "wb") as f:
                    f.write(img_bytes)
                self._send_json({"ok": True, "thumb": thumb_name, "title": og_title, "org": og_site})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
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
