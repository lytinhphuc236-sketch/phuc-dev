"""Phuc Dev AI 4.0 - server cho Render (và chạy thử trên máy).
API key lấy từ biến môi trường GROQ_API_KEY, KHÔNG ghi trong code."""
import os, re, time, uuid, json, hmac, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROV = {  # tên: (địa chỉ API, tên biến môi trường chứa key)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "sambanova": ("https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "cohere": ("https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
}
COHERE_MODELS = ["command-a-03-2025", "command-r-plus-08-2024", "command-r-08-2024", "command-r7b-12-2024"]
ESP_TOKEN = os.environ.get("ESP_TOKEN", "")  # mật khẩu để ESP32 nhận việc
JOBS, ESP = {}, {"seen": 0}  # hàng đợi tệp cho ESP32
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

    def _send(self, code, body=b"", ctype="application/json"):
        if isinstance(body, str): body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else "")); self.end_headers(); self.wfile.write(body)

    def _esp(self):
        if not ESP_TOKEN: self._json(503, "Server chưa cấu hình ESP_TOKEN"); return False
        if not hmac.compare_digest(self.headers.get("X-Esp-Token", "").encode(), ESP_TOKEN.encode()): self._json(401, "Sai token ESP"); return False
        return True

    def _files_get(self):
        if self.path == "/esp/next":  # ESP32 hỏi việc (cũng là tín hiệu "ESP32 đang online")
            if self._esp():
                now = time.time(); ESP["seen"] = now
                job = next((j for j in sorted(JOBS.values(), key=lambda j: j["t"]) if j["status"] == "pending"), None)
                if job:
                    job["status"] = "processing"; job["t0"] = now
                    self._send(200, job["id"] + "\n" + job["name"] + "\n" + job["src"], "text/plain")
                else:
                    self.send_response(204); self.end_headers()
            return True
        m = re.match(r"^/api/files/(\w+)$", self.path)
        if not m: return False
        if self._ok():
            j = JOBS.get(m.group(1)); now = time.time()
            if not j: self._json(404, "Không thấy tác vụ")
            else:
                if j["status"] == "processing" and now - j["t0"] > 170: j["status"], j["error"] = "error", "ESP32 không phản hồi"
                if j["status"] == "pending" and now - j["t"] > 45: j["status"], j["error"] = "error", "ESP32 không nhận việc"
                self._send(200, json.dumps({k: j[k] for k in ("status", "text", "error")}))
        return True

    def _files_post(self):
        if self.path == "/api/files":
            n = int(self.headers.get("Content-Length", 0))
            if n > 400000: self._json(413, "Tệp quá lớn"); return True
            raw = self.rfile.read(n)
            if self._ok():
                now = time.time()
                if now - ESP["seen"] > 20: self._send(200, '{"esp": false}')
                else:
                    try:
                        d = json.loads(raw); name, text = str(d["name"])[:80].replace("\n", " "), str(d["text"])
                    except Exception:
                        self._json(400, "Dữ liệu sai"); return True
                    for k in [k for k, j in JOBS.items() if now - j["t"] > 900]: del JOBS[k]
                    i = uuid.uuid4().hex[:12]
                    JOBS[i] = {"id": i, "name": name, "src": text, "t": now, "status": "pending", "text": "", "error": ""}
                    self._send(200, json.dumps({"esp": True, "id": i}))
            return True
        m = re.match(r"^/esp/result/(\w+)$", self.path)
        if not m: return False
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self._esp():
            j = JOBS.get(m.group(1))
            if j:
                try:  # ESP32 gửi nguyên phản hồi của AI, server tự lấy phần chữ
                    d = json.loads(raw.decode("utf-8", "replace"))
                    if not (isinstance(d, dict) and "choices" in d): raise ValueError(str(d.get("error") if isinstance(d, dict) else d))
                    c = d["choices"][0]["message"]["content"]
                    if isinstance(c, list): c = "".join(x.get("text", "") for x in c)
                    j["text"], j["status"] = c.strip(), "done"
                except Exception as e:
                    j["status"], j["error"] = "error", str(e)[:300]
                j.pop("src", None)
            self._send(200, "{}")
        return True

    def do_GET(self):
        if self._files_get(): return
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
        if self._files_post(): return
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
