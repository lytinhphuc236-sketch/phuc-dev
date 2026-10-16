"""Phuc Dev AI 4.0 - server cho Render (và chạy thử trên máy).
API key lấy từ biến môi trường GROQ_API_KEY, KHÔNG ghi trong code."""
import os, json, hmac, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

KEY = os.environ.get("GROQ_API_KEY", "")
ACCESS = os.environ.get("ACCESS_CODE", "")  # tùy chọn: mã truy cập để người lạ không xài hết key
BASE = "https://api.groq.com/openai/v1"
HERE = os.path.dirname(os.path.abspath(__file__))


class H(BaseHTTPRequestHandler):
    def _json(self, code, msg):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"error": {"message": msg}}).encode())

    def _ok(self):
        if not KEY:
            self._json(500, "Server chưa cấu hình GROQ_API_KEY"); return False
        if ACCESS and not hmac.compare_digest(self.headers.get("X-Access-Code", "").encode(), ACCESS.encode()):
            self._json(401, "Sai mã truy cập"); return False
        return True

    def _up(self, path, data=None):
        req = urllib.request.Request(BASE + path, data=data, headers={
            "Authorization": "Bearer " + KEY, "Content-Type": "application/json",
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

    def do_GET(self):
        if self.path == "/api/models":
            if self._ok(): self._up("/models")
        elif self.path in ("/", "/index.html"):
            body = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/api/chat":
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            if self._ok(): self._up("/chat/completions", body)
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    if not KEY: print("CANH BAO: chua dat bien moi truong GROQ_API_KEY")
    print("Phuc Dev AI 4.0 dang chay o cong", port)
    ThreadingHTTPServer((host, port), H).serve_forever()
