"""Phuc Dev AI 4.0 - server cho Render (và chạy thử trên máy).
API key lấy từ biến môi trường GROQ_API_KEY, KHÔNG ghi trong code."""
import os, re, time, uuid, json, hmac, base64, hashlib, secrets, urllib.parse, urllib.request, urllib.error
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROV = {  # tên: (địa chỉ API, tên biến môi trường chứa key)
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "sambanova": ("https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "cohere": ("https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
}
COHERE_MODELS = ["command-a-03-2025", "command-r-plus-08-2024", "command-r-08-2024", "command-r7b-12-2024"]
ESP_TOKEN = os.environ.get("ESP_TOKEN", "")  # mật khẩu để ESP32 nhận việc
JOBS, ESP = {}, {"seen": 0, "status": {}}  # hàng đợi tệp + status WiFi từ ESP32
CHAT_HITS = {}  # giới hạn cơ bản: 30 lượt chat / IP / 10 phút khi chat công khai
SECRET = os.environ.get("SESSION_SECRET", "")  # chuỗi ngẫu nhiên dài để ký phiên đăng nhập
OA = {p: {"id": os.environ.get(p.upper() + "_CLIENT_ID", ""), "sec": os.environ.get(p.upper() + "_CLIENT_SECRET", "")} for p in ("google", "github")}
LOGIN_ON = bool(SECRET and any(v["id"] and v["sec"] for v in OA.values()))
ALLOWED = {x.strip().lower() for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()}  # email hoặc tên GitHub; trống = ai đăng nhập cũng dùng được
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # token GitHub nằm ở server, không xuống trình duyệt
ADMIN_PASS = os.environ.get("ADMIN_PASS", "1")  # mật khẩu panel (Render có thể ghi đè biến môi trường)
ACCESS = os.environ.get("ACCESS_CODE", "")  # tùy chọn: mã truy cập để người lạ không xài hết key
HERE = os.path.dirname(os.path.abspath(__file__))


def b64(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")
def sign(s): return b64(hmac.new(SECRET.encode(), s.encode(), hashlib.sha256).digest())
def mk_cookie(d): p = b64(json.dumps(d).encode()); return p + "." + sign(p)
def rd_cookie(v):
    try:
        p, sg = v.split(".")
        if not hmac.compare_digest(sg, sign(p)): return None
        d = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        return d if d.get("exp", 0) > time.time() else None
    except Exception:
        return None


class H(BaseHTTPRequestHandler):
    def _json(self, code, msg):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"error": {"message": msg}}).encode())

    def _cookie(self, name):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c[name].value if name in c else ""

    def _user(self):
        d = rd_cookie(self._cookie("pd_sess")) if LOGIN_ON else None
        return d if d and (not ALLOWED or d["id"].lower() in ALLOWED or d.get("email", "").lower() in ALLOWED) else None

    def _ok(self, public_ai=False):
        # AI chat/model list can be used without the former access-code prompt.
        # Requests still go through the configured provider keys on the server.
        if public_ai:
            if self.command == "POST" and "/chat" in self.path:
                ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]
                now = time.time()
                hits = [t for t in CHAT_HITS.get(ip, []) if now - t < 600]
                if len(hits) >= 30:
                    self._json(429, "Bạn đã gửi quá nhiều yêu cầu. Hãy thử lại sau vài phút.")
                    return False
                hits.append(now); CHAT_HITS[ip] = hits
            return True
        hd = self.headers
        if self._user(): return True
        if ACCESS and hmac.compare_digest(hd.get("X-Access-Code", "").encode(), ACCESS.encode()): return True
        if ESP_TOKEN and hmac.compare_digest(hd.get("X-Esp-Token", "").encode(), ESP_TOKEN.encode()): return True
        if not ACCESS and not LOGIN_ON: return True
        self._json(401, "Cần đăng nhập hoặc mã truy cập"); return False

    def _redir(self, url, cookies=()):
        self.send_response(302); self.send_header("Location", url)
        for c in cookies: self.send_header("Set-Cookie", c)
        self.end_headers()

    def _exchange(self, p, code, ru):
        o = OA[p]; ua = {"User-Agent": "PhucDev/4.0", "Accept": "application/json"}
        form = urllib.parse.urlencode({"client_id": o["id"], "client_secret": o["sec"], "code": code, "redirect_uri": ru, "grant_type": "authorization_code"}).encode()
        turl = "https://oauth2.googleapis.com/token" if p == "google" else "https://github.com/login/oauth/access_token"
        t = json.load(urllib.request.urlopen(urllib.request.Request(turl, form, ua), timeout=20))["access_token"]
        A = dict(ua, Authorization="Bearer " + t)
        get = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers=A), timeout=20))
        if p == "google":
            u = get("https://openidconnect.googleapis.com/v1/userinfo")
            if not u.get("email_verified"): raise ValueError("email chưa xác minh")
            return {"p": p, "id": u["email"], "email": u["email"], "name": u.get("name", ""), "pic": u.get("picture", "")}
        u = get("https://api.github.com/user"); email = u.get("email") or ""
        try: email = next(e["email"] for e in get("https://api.github.com/user/emails") if e.get("primary") and e.get("verified"))
        except Exception: pass
        return {"p": p, "id": u["login"], "email": email, "name": u.get("name") or u["login"], "pic": u.get("avatar_url", "")}

    def _auth_get(self):
        if not self.path.startswith("/auth/"): return False
        proto = self.headers.get("X-Forwarded-Proto", "http"); base = proto + "://" + self.headers.get("Host", "")
        sec = "; Secure" if proto == "https" else ""
        if self.path == "/auth/me":
            u = self._user()
            self._send(200, json.dumps({"on": LOGIN_ON, "providers": {p: bool(LOGIN_ON and OA[p]["id"] and OA[p]["sec"]) for p in OA},
                                        "user": {k: u[k] for k in ("p", "id", "name", "pic")} if u else None}))
            return True
        m = re.match(r"^/auth/(google|github)/login$", self.path)
        if m:
            p = m.group(1); o = OA[p]
            if not (LOGIN_ON and o["id"] and o["sec"]): self._json(503, "Server chưa cấu hình đăng nhập " + p); return True
            st = secrets.token_urlsafe(16)
            q = {"client_id": o["id"], "redirect_uri": base + "/auth/" + p + "/callback", "state": st}
            if p == "google": q.update(response_type="code", scope="openid email profile"); url = "https://accounts.google.com/o/oauth2/v2/auth?"
            else: q["scope"] = "read:user user:email"; url = "https://github.com/login/oauth/authorize?"
            self._redir(url + urllib.parse.urlencode(q), ["pd_st=%s; Path=/; Max-Age=600; HttpOnly; SameSite=Lax%s" % (st, sec)])
            return True
        m = re.match(r"^/auth/(google|github)/callback\?(.*)$", self.path)
        if m:
            p, q = m.group(1), urllib.parse.parse_qs(m.group(2))
            if not LOGIN_ON or not q.get("code") or q.get("state", [""])[0] != self._cookie("pd_st"):
                self._redir("/?login=fail"); return True
            try: d = self._exchange(p, q["code"][0], base + "/auth/" + p + "/callback")
            except Exception: self._redir("/?login=fail"); return True
            d["exp"] = time.time() + 30 * 86400
            old = self._user; self._user = lambda: d
            ok = bool(self._user()); self._user = old
            if not ok: self._redir("/?login=denied", ["pd_st=; Path=/; Max-Age=0"]); return True
            self._redir("/", ["pd_sess=%s; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax%s" % (mk_cookie(d), sec), "pd_st=; Path=/; Max-Age=0"])
            return True
        self._json(404, "Không có"); return True

    def _auth_post(self):
        if self.path != "/auth/logout": return False
        self.send_response(200); self.send_header("Set-Cookie", "pd_sess=; Path=/; Max-Age=0"); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
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

    def _gh(self, meth):  # cầu nối GitHub cho admin: /api/gh/<đường dẫn GitHub API>
        if not self.path.startswith("/api/gh/"): return False
        n = int(self.headers.get("Content-Length", 0)); data = self.rfile.read(n) if n else None
        if not (GH_TOKEN and ADMIN_PASS): self._json(503, "Server chưa cấu hình GITHUB_TOKEN / ADMIN_PASS"); return True
        if not hmac.compare_digest(self.headers.get("X-Admin-Pass", "").encode(), ADMIN_PASS.encode()): self._json(401, "Sai mật khẩu admin"); return True
        p = self.path[8:]
        if ".." in p or not re.match(r"^(ping$|user/repos|repos/[\w.-]+/[\w.-]+/(git/trees|contents))", p): self._json(403, "Đường dẫn không được phép"); return True
        if p == "ping": self._send(200, "{}"); return True
        req = urllib.request.Request("https://api.github.com/" + p, data=data, method=meth, headers={"Authorization": "Bearer " + GH_TOKEN, "Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "PhucDev/4.0"})
        try: r = urllib.request.urlopen(req, timeout=30); code = r.status
        except urllib.error.HTTPError as e: r = e; code = e.code
        except Exception as e: self._json(502, str(e)); return True
        self._send(code, r.read()); return True

    def _files_get(self):
        if self.path == "/esp/next":  # ESP32 hỏi việc (cũng là tín hiệu "ESP32 đang online")
            if self._esp():
                end = time.time() + 15
                while True:  # giữ kết nối tới 15 giây để nhận việc ngay khi có tệp
                    now = time.time(); ESP["seen"] = now
                    job = next((j for j in sorted(JOBS.values(), key=lambda j: j["t"]) if j["status"] == "pending"), None)
                    if job or now > end: break
                    time.sleep(0.3)
                if job:
                    job["status"] = "processing"; job["t0"] = now
                    self._send(200, job["id"] + "\n" + job["name"] + "\n" + job["src"], "text/plain")
                else:
                    self.send_response(204); self.end_headers()
            return True
        if self.path == "/api/esp-status":
            if self._ok():
                now = time.time()
                st = dict(ESP.get("status") or {})
                st["online"] = (now - ESP.get("seen", 0)) < 25
                st["last_seen"] = int(ESP.get("seen", 0))
                self._send(200, json.dumps(st))
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
        if self.path == "/esp/status":
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            if self._esp():
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                    if not isinstance(d, dict): raise ValueError("not dict")
                    ESP["status"] = d
                    ESP["seen"] = time.time()
                    self._send(200, "{}")
                except Exception as e:
                    self._json(400, str(e)[:100])
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
        if self._auth_get() or self._files_get() or self._gh("GET"): return
        rt = self._route()
        if rt and rt[1] == "models":
            if not self._ok(public_ai=True): return
            if rt[0] == "cohere":
                if not os.environ.get("COHERE_API_KEY"): return self._json(503, "Chưa cấu hình COHERE_API_KEY")
                body = json.dumps({"data": [{"id": i} for i in COHERE_MODELS]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                return self.wfile.write(body)
            return self._up(rt[0], "/models")
        if urllib.parse.urlsplit(self.path).path in ("/", "/index.html", "/ai", "/gmail"):
            body = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self._auth_post() or self._files_post(): return
        rt = self._route()
        if rt and rt[1] == "chat":
            n = int(self.headers.get("Content-Length", 0))
            if n > 150000: return self._json(413, "Tin nhắn quá lớn (giới hạn 150 KB)")
            body = self.rfile.read(n)
            if self._ok(public_ai=True): self._up(rt[0], "/chat/completions", body)
        else:
            self.send_response(404); self.end_headers()

    def do_PUT(self):
        if not self._gh("PUT"): self.send_response(404); self.end_headers()

    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    print("dang nhap:", "BAT" if LOGIN_ON else "tat (can SESSION_SECRET + client id/secret)")
    for p, (_, env) in PROV.items():
        print(p, "OK" if os.environ.get(env) else "chua co " + env)
    print("Phuc Dev AI 4.0 dang chay o cong", port)
    ThreadingHTTPServer((host, port), H).serve_forever()