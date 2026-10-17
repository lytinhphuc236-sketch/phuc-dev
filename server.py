"""Phuc Dev AI 4.0 - server cho Render (và chạy thử trên máy).
API key lấy từ biến môi trường GROQ_API_KEY, KHÔNG ghi trong code."""
import os, re, json, hmac, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROV = {  # tên: (địa chỉ API, tên biến môi trường chứa key)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "sambanova": ("https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "cohere": ("https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
}
COHERE_MODELS = ["command-a-03-2025", "command-r-plus-08-2024", "command-r-08-2024", "command-r7b-12-2024"]
ACCESS = os.environ.get("ACCESS_CODE", "")  # tùy chọn: mã truy cập để người lạ không xài hết key
HERE = os.path.dirname(os.path.abspath(__file__))


class H(BaseHTTPRequestHandler):
    def _json(self, code, msg):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"error": {"message": msg}}).encode())

    def _ok(self):
        if ACCESS and not hmac.compare_digest(self.headers.get("X-Access-Code", "").encode(), ACCESS.encode()):
            self._json(401, "Sai mã truy cập"); return False
        return True

    def _up(self, prov, path, data=None):
        base, env = PROV[prov]; key = os.environ.get(env, "")
        if not key:
            return self._json(503, "Server chưa cấu hình " + env)
        req = urllib.request.Request(base + path, data=data, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "User-Agent": "PhucDev/4.0"})
        try:
            r = urllib.request.urlopen(req, timeout=120); code = r.status
        except urllib.error.HTTPError as e:
            r = e; code = e.code
        except Exception as e:
            return self._json(502, str(e))
        self.send_response(code)
        self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
        self.send_header("Cache-Control", "no-cache"); self.end_headers()
        try:
            while True:
                b = r.read1(4096) if hasattr(r, "read1") else r.read(4096)
                if not b: break
                self.wfile.write(b); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _route(self):
        m = re.match(r"^/api/(?:(\w+)/)?(chat|models)$", self.path)
        if not m: return None
        prov = m.group(1) or "groq"
        return (prov, m.group(2)) if prov in PROV else None

    def do_GET(self):
        rt = self._route()
        if rt and rt[1] == "models":
            if not self._ok(): return
            if rt[0] == "cohere":
                if not os.environ.get("COHERE_API_KEY"): return self._json(503, "Chưa cấu hình COHERE_API_KEY")
                body = json.dumps({"data": [{"id": i} for i in COHERE_MODELS]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                return self.wfile.write(body)
            return self._up(rt[0], "/models")
        if self.path in ("/", "/index.html"):
            body = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        rt = self._route()
        if rt and rt[1] == "chat":
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            if self._ok(): self._up(rt[0], "/chat/completions", body)
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    for p, (_, env) in PROV.items():
        print(p, "OK" if os.environ.get(env) else "chua co " + env)
    print("Phuc Dev AI 4.0 dang chay o cong", port)
    ThreadingHTTPServer((host, port), H).serve_forever()
