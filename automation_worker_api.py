"""
Module automation_worker_api.py
Bộ điều phối quy trình tự động hóa (Automation Worker) sử dụng TempMail API:
- Tương tác TempMail bằng API `tempmail-lol` thay vì Playwright
- Có giới hạn tốc độ API (Rate Limit) thông qua `api_rate_limiter.global_rate_limiter`
- Chỉ mở 1 Tab Playwright (Target Website)
"""

import asyncio
import time
import logging
import re
from datetime import datetime
from typing import Callable, Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

import requests
from api_rate_limiter import global_rate_limiter

from selectors import DEFAULT_TARGET_URL
from target_service import (
    fill_email_and_request_code,
    resend_code_if_available,
    fill_otp_and_verify,
    enter_app_and_complete_profile,
    process_circles,
    logout_and_prepare_next_target_session,
    ensure_matching_email_on_target,
)
from ai_service import ModelAi
from sleep_preventer import sleep_preventer

logger = logging.getLogger("AutomationWorkerAPI")


class AutomationWorkerAPI:
    def __init__(
        self,
        worker_id: int = 1,
        total_workflows: int = 20,
        refresh_interval: int = 15,
        otp_timeout: int = 120,
        headless: bool = False,
        target_url: str = DEFAULT_TARGET_URL,
        circle_urls: Optional[list] = None,
        delay_between_workflows: float = 5,
        delay_between_circles: float = 1,
        api_key_ai: str = "",
        ai_base_url: str = "https://api1.shupremium.com/v1",
        ai_model: str = "gpt-4o-mini",
        custom_selectors: Optional[Dict[str, str]] = None,
        ui_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        self.worker_id = int(worker_id)
        self.total_workflows = int(total_workflows)
        self.refresh_interval = int(refresh_interval)
        self.otp_timeout = int(otp_timeout)
        self.headless = headless
        self.target_url = target_url or DEFAULT_TARGET_URL
        self.circle_urls = circle_urls or []
        self.delay_between_workflows = float(delay_between_workflows)
        self.delay_between_circles = float(delay_between_circles)
        self.api_key_ai = api_key_ai
        self.ai_base_url = ai_base_url
        self.ai_model = ai_model
        self.ai_model_instance = ModelAi(api_key=api_key_ai, base_url=ai_base_url, model=ai_model)
        
        # Không còn cấu hình TempMail API Key (dùng mặc định)
        
        self.custom_selectors = custom_selectors or {}
        self.ui_callback = ui_callback

        # Trạng thái điều khiển
        self.is_running = False
        self.is_paused = False
        self._stop_requested = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

        # Playwright
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.target_page: Optional[Page] = None

    def log(self, message: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        full_line = f"{now_str} [Luồng API {self.worker_id}] {message}"
        logger.info(full_line)
        if self.ui_callback:
            self.ui_callback("log", {"line": full_line, "worker_id": self.worker_id})

    def update_ui_status(self, status: str):
        if self.ui_callback:
            self.ui_callback("status", {"status": status, "worker_id": self.worker_id})

    def update_ui_progress(self, current: int, total: int, email: str = ""):
        if self.ui_callback:
            self.ui_callback("progress", {"current": current, "total": total, "email": email, "worker_id": self.worker_id})

    def update_ui_checklist(self, **kwargs):
        if self.ui_callback and kwargs:
            kwargs["worker_id"] = self.worker_id
            self.ui_callback("checklist", kwargs)

    def pause(self):
        self.is_paused = True
        self._pause_event.clear()
        self.update_ui_status("PAUSED")
        self.log("Worker đã tạm dừng (PAUSED)")

    def resume(self):
        self.is_paused = False
        self._pause_event.set()
        self.update_ui_status("RUNNING")
        self.log("Worker tiếp tục chạy (RESUMED)")

    def stop(self):
        self._stop_requested = True
        self.is_running = False
        self._pause_event.set()
        self.update_ui_status("STOPPED")
        self.log("Đã yêu cầu dừng toàn bộ Worker (STOPPED)")

    async def _check_pause_or_stop(self):
        if self._stop_requested:
            raise asyncio.CancelledError("Worker stopped by user")
        await self._pause_event.wait()
        if self._stop_requested:
            raise asyncio.CancelledError("Worker stopped by user")

    async def _get_new_inbox(self):
        """Tạo hòm thư mới qua api.tempmailportal.com (rate limit)"""
        await global_rate_limiter.wait_if_needed()
        self.log("Gửi request tạo TempMail Inbox (qua tempmailportal.com)...")
        
        def do_request():
            resp = requests.post("https://api.tempmailportal.com/api/inbox", timeout=15)
            resp.raise_for_status()
            return resp.json()

        loop = asyncio.get_event_loop()
        try:
            inbox = await loop.run_in_executor(None, do_request)
            return inbox
        except Exception as e:
            self.log(f"Lỗi khi tạo inbox bằng API: {e}")
            return None

    async def _check_emails(self, token: str):
        """Kiểm tra email qua api.tempmailportal.com (limit 120/min per mailbox)"""
        # Không cần dùng global_rate_limiter ở đây vì limit là tính trên mỗi email (poll mỗi 8-10s là an toàn)
        def do_request():
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get("https://api.tempmailportal.com/api/messages", headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()

        loop = asyncio.get_event_loop()
        try:
            emails = await loop.run_in_executor(None, do_request)
            return emails
        except Exception as e:
            self.log(f"Lỗi khi lấy danh sách emails từ API: {e}")
            return []

    def _extract_otp_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        
        # 1. Mẫu OTP có từ khóa chỉ dẫn
        pattern_strict = [
            r'(?:mã|otp|code|mã xác minh|mã xác thực|verification code)[\s:=#\-]+([0-9]{4,8})\b',
            r'\b([0-9]{4,8})[\s]+(?:là mã|is your code|is your otp|để đăng nhập|để xác minh)',
        ]
        for p in pattern_strict:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                return match.group(1)

        # 2. Mẫu 6 chữ số phổ biến
        six_digit_match = re.search(r'\b([0-9]{6})\b', text)
        if six_digit_match:
            return six_digit_match.group(1)

        # 3. Mẫu 4 chữ số
        four_digit_match = re.search(r'\b([0-9]{4})\b', text)
        if four_digit_match:
            return four_digit_match.group(1)
            
        return None

    async def run(self):
        self.is_running = True
        self._stop_requested = False
        self._pause_event.set()
        self.update_ui_status("RUNNING")
        
        self.log("Khởi động trình duyệt Playwright Chromium (Target only)...")
        try:
            sleep_preventer.prevent_sleep("UCircle API Automation Running")
            self.playwright = await async_playwright().start()

            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
            if not self.headless:
                args.append("--start-maximized")

            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=args
            )

            self.context = await self.browser.new_context(
                no_viewport=(not self.headless),
                viewport={"width": 1280, "height": 720} if self.headless else None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                locale="vi-VN"
            )

            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # ----------------------------------------------------
            # Mở tab duy nhất (Target Website)
            # ----------------------------------------------------
            self.target_page = await self.context.new_page()
            self.log(f"Mở Target Website: {self.target_url}")
            await self.target_page.goto(self.target_url, wait_until="domcontentloaded", timeout=45000)

            # ----------------------------------------------------
            # VÒNG LẶP WORKFLOWS
            # ----------------------------------------------------
            for wf_idx in range(1, self.total_workflows + 1):
                await self._check_pause_or_stop()

                self.update_ui_progress(current=wf_idx, total=self.total_workflows, email="(Đang tạo bằng API...)")
                self.update_ui_checklist(
                    register="-",
                    send_otp="-",
                    waiting_email="-",
                    refresh_count=0,
                    otp="Waiting...",
                    verify="-",
                    tasks="Running"
                )

                self.log(f"=== Bắt đầu Workflow #{wf_idx} / {self.total_workflows} ===")
                
                # Tạo Inbox mới bằng API
                current_inbox = await self._get_new_inbox()
                if not current_inbox:
                    self.log("✗ Không thể tạo được email tạm thời qua API. Đang thử lại...")
                    await asyncio.sleep(3)
                    current_inbox = await self._get_new_inbox()
                    if not current_inbox:
                        self.log("✗ Đã thất bại lần 2. Bỏ qua workflow này.")
                        continue
                
                current_email = current_inbox.get('address')
                inbox_token = current_inbox.get('token')
                
                self.log(f"Current Email (API): {current_email}")
                self.update_ui_progress(current=wf_idx, total=self.total_workflows, email=current_email)

                success = await self._run_single_workflow(wf_idx, current_email, inbox_token)

                if success:
                    self.update_ui_checklist(tasks="Completed")
                    self.log(f"✓ Hoàn thành Workflow #{wf_idx} thành công!")
                else:
                    self.update_ui_checklist(tasks="Failed")
                    self.log(f"✗ Workflow #{wf_idx} không thành công hoặc hết thời gian chờ.")

                # Chuẩn bị cho workflow kế tiếp: Nghỉ ngơi theo quy định
                if wf_idx < self.total_workflows and not self._stop_requested:
                    if self.delay_between_workflows > 0:
                        self.log(f"Bắt đầu nghỉ ngơi {self.delay_between_workflows}s theo quy định...")
                        total_secs = int(self.delay_between_workflows)
                        if total_secs >= 1:
                            for rem in range(total_secs, 0, -1):
                                await self._check_pause_or_stop()
                                self.update_ui_checklist(tasks=f"Nghỉ ({rem}s)")
                                await asyncio.sleep(1)
                        rem_fraction = self.delay_between_workflows - total_secs
                        if rem_fraction > 0:
                            await asyncio.sleep(rem_fraction)

            self.log("Tất cả workflows đã hoàn thành!")
            self.update_ui_status("COMPLETED")

        except asyncio.CancelledError:
            self.log("Worker đã nhận lệnh hủy, đang thoát an toàn...")
        except Exception as e:
            self.log(f"Lỗi hệ thống: {e}")
            self.update_ui_status("ERROR")
        finally:
            sleep_preventer.allow_sleep()
            await self._cleanup()

    async def _run_single_workflow(self, wf_idx: int, email: str, token: str) -> bool:
        try:
            # ----------------------------------------------------
            # BƯỚC 1: Chuyển sang TARGET WEBSITE
            # ----------------------------------------------------
            if self.target_page.is_closed():
                self.target_page = await self.context.new_page()
            
            if "/auth/login" not in self.target_page.url:
                await self.target_page.goto(self.target_url, wait_until="domcontentloaded", timeout=30000)

            await self._check_pause_or_stop()

            # ----------------------------------------------------
            # BƯỚC 2: Điền email và nhấn "Gửi mã"
            # ----------------------------------------------------
            self.log(f"Điền email: {email} và bấm Gửi mã...")
            req_ok = await fill_email_and_request_code(self.target_page, email, self.custom_selectors)
            if not req_ok:
                self.log("Không thể hoàn tất bước gửi mã trên Target Page!")
                return False

            self.update_ui_checklist(register="✓", send_otp="✓")
            self.log("Registration submitted")
            self.log("OTP requested")

            await self._check_pause_or_stop()

            # ----------------------------------------------------
            # BƯỚC 3: Vòng lặp chờ OTP qua API
            # ----------------------------------------------------
            self.log("Đang gọi API kiểm tra hộp thư...")
            self.update_ui_checklist(waiting_email="⟳")
            otp_found = None
            refresh_count = 0
            has_resent = False
            start_wait_time = time.time()

            while time.time() - start_wait_time < self.otp_timeout:
                await self._check_pause_or_stop()
                await asyncio.sleep(self.refresh_interval)

                refresh_count += 1
                self.update_ui_checklist(refresh_count=refresh_count)
                self.log(f"Lấy API Inbox lần #{refresh_count}...")

                # Kiểm tra thư đến qua API
                emails = await self._check_emails(token)

                # Trường hợp test với Mock Server
                if not emails and "127.0.0.1:5000" in self.target_url:
                    from mock_server import MOCK_OTP_STORAGE
                    mock_otp = MOCK_OTP_STORAGE.get(email)
                    if mock_otp and refresh_count >= 2:
                        self.log("Mock Server OTP found")
                        otp_found = mock_otp
                        self.log(f"OTP extracted: {otp_found}")
                        self.update_ui_checklist(waiting_email="✓", otp=otp_found)
                        break

                if emails:
                    self.log(f"Tìm thấy {len(emails)} thư mới qua API!")
                    
                    for mail in emails:
                        # mail bây giờ là một dictionary từ JSON
                        sender = mail.get('sender', '') or mail.get('from', '')
                        sender = sender.lower()
                        subject = mail.get('subject', '').lower()
                        
                        keywords = ["ucircle", "otp", "code", "mã", "xác minh", "xác thực", "verify"]
                        if any(kw in subject or kw in sender for kw in keywords):
                            self.log("Đây là thư UCircle!")
                            self.update_ui_checklist(waiting_email="✓")
                            
                            # Tìm OTP trong nội dung
                            # Gộp toàn bộ các value chữ (text/html/body) trả về từ API để không bao giờ bị trượt mất OTP
                            full_text = " ".join([str(v) for v in mail.values() if isinstance(v, str)])
                            
                            # Xóa các thẻ HTML thành dấu cách để regex dễ bắt
                            clean_text = re.sub(r'<[^>]+>', ' ', full_text)
                            
                            otp_found = self._extract_otp_from_text(clean_text)
                            
                            if not otp_found:
                                self.log(f"DEBUG CHƯA TÌM THẤY MÃ TRONG THƯ NÀY: {clean_text[:200]}...")
                            
                            if otp_found:
                                self.log(f"OTP extracted từ API: {otp_found}")
                                self.update_ui_checklist(otp=otp_found)
                                break
                    if otp_found:
                        break

                # (Đã gỡ bỏ logic "Gửi lại mã sau 3 lần" vì API sẽ tự chờ thư tới)

            if not otp_found:
                self.log(f"Timeout {self.otp_timeout}s: Không nhận được mã OTP!")
                return False

            await self._check_pause_or_stop()

            # ----------------------------------------------------
            # BƯỚC 4: Điền OTP & xác minh
            # ----------------------------------------------------
            self.log("Điền mã OTP và xác minh trên Target Website...")

            verify_ok = await fill_otp_and_verify(self.target_page, otp_found, self.custom_selectors)
            if not verify_ok:
                self.update_ui_checklist(verify="✗")
                self.log("Không thể xác minh mã OTP trên Target Page!")
                return False

            self.update_ui_checklist(verify="✓")
            self.log("Account verified (Đăng nhập thành công)")

            # ----------------------------------------------------
            # BƯỚC 5: Hoàn thiện hồ sơ Onboarding
            # ----------------------------------------------------
            self.log("Tiến hành Vào UCircle và thiết lập hồ sơ người dùng...")
            profile_ok = await enter_app_and_complete_profile(
                self.target_page,
                email,
                ai_model_instance=self.ai_model_instance
            )
            if profile_ok:
                self.log("✓ Thiết lập hồ sơ UCircle hoàn tất!")
            else:
                self.log("Cảnh báo: Không thể hoàn tất hộp thoại hồ sơ (có thể tài khoản đã có hồ sơ trước đó)")

            await asyncio.sleep(0.5)

            # ----------------------------------------------------
            # BƯỚC 6: Theo dõi và Tham gia danh sách Circle
            # ----------------------------------------------------
            if self.circle_urls:
                self.log(f"Bắt đầu xử lý {len(self.circle_urls)} Circle(s) mục tiêu...")
                self.update_ui_checklist(tasks="Joining Circles")
                done_circles = await process_circles(
                    self.target_page,
                    self.circle_urls,
                    delay_between_circles=self.delay_between_circles,
                    log_cb=self.log
                )
                self.update_ui_checklist(tasks=f"Circles ({done_circles}/{len(self.circle_urls)})")
                self.log(f"✓ Đã hoàn thành theo dõi & tham gia {done_circles}/{len(self.circle_urls)} Circle!")

            # ----------------------------------------------------
            # BƯỚC 7: Đăng xuất
            # ----------------------------------------------------
            self.log("Tiến hành Đăng xuất UCircle để làm sạch phiên (giữ tab mở)...")
            self.target_page = await logout_and_prepare_next_target_session(
                self.target_page,
                self.context,
                self.target_url
            )
            self.log("Đã chuẩn bị tab Target sẵn sàng cho luồng tiếp theo...")
            await asyncio.sleep(1)
            return True

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.log(f"Lỗi trong quá trình thực thi workflow: {e}")
            return False
        finally:
            if self.target_page and not self.target_page.is_closed():
                await logout_and_prepare_next_target_session(self.target_page, self.context, self.target_url)

    async def _cleanup(self):
        self.is_running = False
        try:
            if self.target_page and not self.target_page.is_closed():
                await self.target_page.close()
        except Exception:
            pass

        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass

        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass

        self.log("Đã đóng và dọn dẹp tài nguyên Playwright.")
