"""
Module mock_server.py
Cung cấp một Mock Target Website cục bộ chạy trên http://127.0.0.1:5000/register
để phục vụ việc kiểm thử luồng 2 tab:
- Nhập email
- Bấm "Gửi mã"
- Đếm ngược và hiển thị ô nhập OTP
- Nhập mã và xác nhận thành công
"""

import http.server
import socketserver
import threading
import json
import logging
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("MockServer")

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mock Target Website - Đăng ký tài khoản</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #0f172a, #1e293b); color: #f8fafc; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 32px; width: 100%; max-width: 440px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
        h2 { font-size: 24px; font-weight: 700; margin-bottom: 8px; color: #38bdf8; text-align: center; }
        p.subtitle { font-size: 14px; color: #94a3b8; margin-bottom: 24px; text-align: center; }
        .form-group { margin-bottom: 18px; }
        label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
        input[type="text"], input[type="email"] { width: 100%; padding: 12px 14px; background: #0f172a; border: 1px solid #475569; border-radius: 8px; color: #f8fafc; font-size: 14px; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: #38bdf8; }
        .btn { width: 100%; padding: 12px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-primary { background: #0284c7; color: white; margin-top: 8px; }
        .btn-primary:hover { background: #0369a1; }
        .btn-primary:disabled { background: #475569; cursor: not-allowed; opacity: 0.7; }
        .btn-success { background: #10b981; color: white; margin-top: 12px; }
        .btn-success:hover { background: #059669; }
        .hidden { display: none; }
        .status-msg { margin-top: 16px; padding: 12px; border-radius: 8px; font-size: 13px; text-align: center; }
        .status-msg.info { background: #082f49; border: 1px solid #0284c7; color: #38bdf8; }
        .status-msg.success { background: #064e3b; border: 1px solid #10b981; color: #34d399; font-weight: 600; font-size: 15px; }
        .status-msg.error { background: #4c0519; border: 1px solid #e11d48; color: #fb7185; }
        .countdown { font-size: 12px; color: #f59e0b; margin-top: 4px; display: block; text-align: right; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Đăng Ký Tài Khoản</h2>
        <p class="subtitle">Target Website Demo - Hỗ trợ kiểm thử Automation</p>

        <form id="regForm" onsubmit="return false;">
            <div class="form-group">
                <label for="email">Địa chỉ Email:</label>
                <input type="email" id="email" name="email" placeholder="Nhập địa chỉ email..." required>
                <button type="button" id="send-otp-btn" class="btn btn-primary" onclick="requestOtp()">Gửi mã OTP</button>
                <span id="countdown" class="countdown hidden"></span>
            </div>

            <div id="otp-group" class="form-group hidden">
                <label for="otp">Mã xác nhận (OTP):</label>
                <input type="text" id="otp" name="otp" placeholder="Nhập 6 chữ số OTP..." maxlength="8">
                <button type="button" id="verify-btn" class="btn btn-success" onclick="verifyOtp()">Xác minh & Đăng ký</button>
            </div>

            <div id="status-msg" class="status-msg hidden"></div>
        </form>
    </div>

    <script>
        let generatedOtp = "";
        let countdownTimer = null;

        function showMessage(text, type) {
            const el = document.getElementById("status-msg");
            el.className = "status-msg " + type;
            el.innerText = text;
            el.classList.remove("hidden");
        }

        async function requestOtp() {
            const email = document.getElementById("email").value.trim();
            if (!email || !email.includes("@")) {
                showMessage("Vui lòng nhập đúng định dạng email!", "error");
                return;
            }

            const sendBtn = document.getElementById("send-otp-btn");
            sendBtn.disabled = true;
            showMessage("Đang gửi mã xác nhận tới " + email + "...", "info");

            try {
                const res = await fetch("/api/send-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email })
                });
                const data = await res.json();
                generatedOtp = data.otp;

                showMessage("Mã OTP đã được gửi tới " + email + "! (Mã test: " + generatedOtp + ")", "info");
                document.getElementById("otp-group").classList.remove("hidden");
                document.getElementById("otp").focus();

                // Đếm ngược 60 giây
                let seconds = 60;
                const cdEl = document.getElementById("countdown");
                cdEl.classList.remove("hidden");
                cdEl.innerText = "Gửi lại sau " + seconds + "s";

                clearInterval(countdownTimer);
                countdownTimer = setInterval(() => {
                    seconds--;
                    if (seconds <= 0) {
                        clearInterval(countdownTimer);
                        sendBtn.disabled = false;
                        cdEl.classList.add("hidden");
                    } else {
                        cdEl.innerText = "Gửi lại sau " + seconds + "s";
                    }
                }, 1000);
            } catch (err) {
                showMessage("Lỗi gửi mã: " + err, "error");
                sendBtn.disabled = false;
            }
        }

        async function verifyOtp() {
            const enteredOtp = document.getElementById("otp").value.trim();
            const email = document.getElementById("email").value.trim();

            if (!enteredOtp) {
                showMessage("Vui lòng nhập mã OTP!", "error");
                return;
            }

            try {
                const res = await fetch("/api/verify-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email, otp: enteredOtp })
                });
                const data = await res.json();
                if (data.success) {
                    showMessage("✓ Xác minh thành công! Tài khoản đã được kích hoạt.", "success");
                    document.getElementById("verify-btn").disabled = true;
                } else {
                    showMessage("Mã OTP không chính xác, vui lòng thử lại!", "error");
                }
            } catch (err) {
                showMessage("Lỗi xác minh: " + err, "error");
            }
        }
    </script>
</body>
</html>
"""

# Lưu OTP tạm theo email
MOCK_OTP_STORAGE = {}


class MockTargetHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Tắt log mặc định của http.server

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/register"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if parsed.path == "/api/send-otp":
            import random
            email = data.get("email", "")
            # Tạo ngẫu nhiên OTP 6 chữ số
            otp = f"{random.randint(100000, 999999)}"
            MOCK_OTP_STORAGE[email] = otp
            logger.info(f"[MockServer] Tạo OTP: {otp} cho email: {email}")

            resp = {"status": "sent", "email": email, "otp": otp}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        elif parsed.path == "/api/verify-otp":
            email = data.get("email", "")
            otp = data.get("otp", "")
            expected = MOCK_OTP_STORAGE.get(email)

            success = bool(otp and (otp == expected or otp == "123456"))
            resp = {"success": success}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class MockServer:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None
        self.running = False

    def start(self):
        if self.running:
            return
        try:
            self.httpd = socketserver.TCPServer((self.host, self.port), MockTargetHandler)
            self.running = True
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"Mock Target Server đang chạy tại http://{self.host}:{self.port}/register")
        except Exception as e:
            logger.error(f"Không thể khởi chạy Mock Server: {e}")

    def stop(self):
        if self.httpd and self.running:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.running = False
            logger.info("Đã dừng Mock Target Server")


# Singleton instance
mock_server_instance = MockServer()

def get_mock_server():
    return mock_server_instance


if __name__ == "__main__":
    server = MockServer()
    server.start()
    print("Mock Server đã chạy trên http://127.0.0.1:5000/register. Nhấn Ctrl+C để thoát.")
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
