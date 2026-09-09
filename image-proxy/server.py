import base64
import hashlib
import ipaddress
import os
import pathlib
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

CACHE = pathlib.Path(os.getenv("CACHE_DIR", "/cache"))
CACHE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(os.getenv("MAX_BYTES", str(15 * 1024 * 1024)))
MAX_CACHE_BYTES = int(os.getenv("MAX_CACHE_BYTES", str(512 * 1024 * 1024)))
TIMEOUT = int(os.getenv("TIMEOUT", "30"))
UA = os.getenv("USER_AGENT", "Mozilla/5.0 RSSImageGateway/1.1")
ALLOW_SVG = os.getenv("ALLOW_SVG", "0").lower() in {"1", "true", "yes", "on"}
REFERERS = {}
for item in os.getenv("REFERERS", "").split(","):
    if "=" in item:
        k, v = item.split("=", 1)
        REFERERS[k.strip().lower()] = v.strip()
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif", "image/bmp", "image/x-icon"}
if ALLOW_SVG:
    ALLOWED_TYPES.add("image/svg+xml")
_CACHE_LOCK = threading.Lock()
_LAST_EVICTION = 0.0


def public_host(host):
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except Exception:
        return False
    ips = {x[4][0] for x in infos}
    if not ips:
        return False
    for raw in ips:
        try:
            ip = ipaddress.ip_address(raw)
            if not ip.is_global:
                return False
        except ValueError:
            return False
    return True


def safe_url(url):
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.hostname) and public_host(p.hostname)


def decode_path(path):
    part = path.split("/proxy/", 1)[1].split("?", 1)[0].strip("/")
    encoded = part.rsplit("/", 1)[-1]
    return base64.urlsafe_b64decode(encoded + "=" * ((4 - len(encoded) % 4) % 4)).decode()


def unwrap_nested_proxy(url):
    for _ in range(3):
        p = urlparse(url)
        if not p.path.startswith("/proxy/"):
            break
        try:
            url = decode_path(p.path)
        except Exception:
            break
    return url


def cache_key(url):
    return hashlib.sha256(url.encode()).hexdigest()


def referer_for(url):
    host = (urlparse(url).hostname or "").lower()
    for domain, ref in REFERERS.items():
        if host == domain or host.endswith("." + domain):
            return ref
    return ""


def evict_cache(force=False):
    global _LAST_EVICTION
    now = time.monotonic()
    if not force and now - _LAST_EVICTION < 60:
        return
    with _CACHE_LOCK:
        _LAST_EVICTION = now
        files = []
        total = 0
        for body in CACHE.glob("*.bin"):
            try:
                stat = body.stat()
                total += stat.st_size
                files.append((stat.st_atime, stat.st_mtime, body, stat.st_size))
            except OSError:
                continue
        if total <= MAX_CACHE_BYTES:
            return
        files.sort(key=lambda x: (x[0], x[1]))
        for _, _, body, size in files:
            if total <= MAX_CACHE_BYTES:
                break
            try:
                body.unlink(missing_ok=True)
                body.with_suffix(".meta").unlink(missing_ok=True)
                total -= size
            except OSError:
                pass


def fetch(url):
    current = url
    for _ in range(5):
        if not safe_url(current):
            raise ValueError("unsafe_target")
        headers = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
        ref = referer_for(current)
        if ref:
            headers["Referer"] = ref
        req = Request(current, headers=headers, method="GET")
        try:
            r = urlopen(req, timeout=TIMEOUT)
            ctype = (r.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            if ctype not in ALLOWED_TYPES:
                raise ValueError("not_image:" + ctype)
            data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("too_large")
            return ctype, data
        except HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                nxt = e.headers.get("Location")
                if not nxt:
                    raise ValueError("redirect_without_location")
                current = urljoin(current, nxt)
                continue
            raise
    raise ValueError("too_many_redirects")


class Handler(BaseHTTPRequestHandler):
    server_version = "RSSImageGateway/1.1"

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def send_bytes(self, status, ctype, data, cached=False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=604800, immutable" if cached else "public, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Image-Gateway", "cache" if cached else "fetch")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_bytes(200, "text/plain; charset=utf-8", b"ok")
            return
        if not self.path.startswith("/proxy/"):
            self.send_error(404)
            return
        try:
            url = unwrap_nested_proxy(decode_path(self.path))
        except Exception:
            self.send_error(400, "bad_url")
            return
        if not safe_url(url):
            self.send_error(403, "unsafe_target")
            return
        key = cache_key(url)
        meta = CACHE / (key + ".meta")
        body = CACHE / (key + ".bin")
        try:
            if meta.exists() and body.exists():
                ctype = meta.read_text().strip()
                data = body.read_bytes()
                os.utime(body, None)
                self.send_bytes(200, ctype, data, True)
                return
            ctype, data = fetch(url)
            tmp = body.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(body)
            meta.write_text(ctype)
            evict_cache()
            self.send_bytes(200, ctype, data, False)
        except HTTPError as e:
            self.send_error(e.code, "upstream_http_error")
        except (URLError, TimeoutError) as e:
            self.send_error(502, "upstream_error")
        except ValueError as e:
            self.send_error(422, str(e))
        except Exception as e:
            print("fetch failure", repr(e), flush=True)
            self.send_error(502, "gateway_error")


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
