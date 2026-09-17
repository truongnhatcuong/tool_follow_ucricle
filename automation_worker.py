"""
Module automation_worker.py
Bộ điều phối quy trình tự động hóa (Automation Worker):
- Quản lý vòng đời Playwright Chromium (Headless ON/OFF)
- Quản lý đồng thời 2 tab: Tab 1 (email tạm), Tab 2 (target website UCircle)
- Tự động bấm "Gửi lại mã" nếu OTP chưa về sau lượt refresh đầu
- Điền OTP, bấm "Vào UCircle" và hoàn thiện hồ sơ (@username, Tên hiển thị, Cho tìm, Lưu & bắt đầu)
- Triển khai chính xác Pseudo flow và cơ chế chỉ reload Tab email
- Hỗ trợ Pause / Resume / Stop thông qua asyncio.Event
- Bắn thông báo cập nhật trạng thái, checklist, đếm refresh và log về GUI
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Callable, Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from selectors import (
    TEMP_MAIL_URL,
    TEMP_MAIL_NEW_URL,
    INBOX_TABLE_SELECTOR,
    DEFAULT_TARGET_URL,
)
from email_service import (
    get_current_email,
    create_next_email,
    get_messages,
    find_verification_email,
    extract_otp,
)
from target_service import (
    fill_email_and_request_code,
    resend_code_if_available,
    fill_otp_and_verify,
    enter_app_and_complete_profile,
    process_circles,
    logout_and_prepare_next_target_session,
    reset_target_session,
    ensure_matching_email_on_target,
)
from ai_service import ModelAi
from sleep_preventer import sleep_preventer

logger = logging.getLogger("AutomationWorker")


class AutomationWorker:
    def __init__(
        self,
        worker_id: int = 1,
        total_workflows: int = 20,
        refresh_interval: int = 20,
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
        self.custom_selectors = custom_selectors or {}
        self.ui_callback = ui_callback

        # Trạng thái điều khiển
        self.is_running = False
        self.is_paused = False
        self._stop_requested = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

        # Các đối tượng Playwright
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.email_page: Optional[Page] = None
        self.target_page: Optional[Page] = None

    def log(self, message: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        full_line = f"{now_str} [Luồng {self.worker_id}] {message}"
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

    async def run(self):
        self.is_running = True
        self._stop_requested = False
        self._pause_event.set()
        self.update_ui_status("RUNNING")
        self.log("Khởi động trình duyệt Playwright Chromium...")
        try:
            sleep_preventer.prevent_sleep("UCircle Automation Running")
            self.log("✓ Đã bật chế độ chống Sleep: Giữ máy tính luôn hoạt động (Stay Awake)!")
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
            # BƯỚC 1: Mở tab 1 (Temporary Email)
            # ----------------------------------------------------
            self.email_page = await self.context.new_page()

            async def block_ads(route):
                url = route.request.url.lower()
                ad_keywords = [
                    "googlesyndication", "google-analytics", "doubleclick",
                    "adservice", "taboola", "criteo", "amazon-adsystem", "fundingchoices"
                ]
                if any(ad in url for ad in ad_keywords):
                    await route.abort()
                else:
                    await route.continue_()

            await self.email_page.route("**/*", block_ads)

            self.log(f"Mở trang email tạm: {TEMP_MAIL_URL}")
            await self.email_page.goto(TEMP_MAIL_URL, wait_until="domcontentloaded", timeout=45000)

            current_email = await get_current_email(self.email_page)
            if not current_email or "@" not in current_email:
                self.log("Email ban đầu chưa sẵn sàng, đang yêu cầu cấp email mới...")
                current_email = await create_next_email(self.email_page)
            self.log(f"Created email: {current_email}")

            # ----------------------------------------------------
            # VÒNG LẶP WORKFLOWS
            # ----------------------------------------------------
            for wf_idx in range(1, self.total_workflows + 1):
                await self._check_pause_or_stop()

                self.update_ui_progress(current=wf_idx, total=self.total_workflows, email=current_email)
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
                self.log(f"Current Email: {current_email}")

                success = await self._run_single_workflow(wf_idx, current_email)

                if success:
                    self.update_ui_checklist(tasks="Completed")
                    self.log(f"✓ Hoàn thành Workflow #{wf_idx} thành công!")
                else:
                    self.update_ui_checklist(tasks="Failed")
                    self.log(f"✗ Workflow #{wf_idx} không thành công hoặc hết thời gian chờ.")

                # Chuẩn bị cho workflow kế tiếp: Nghỉ ngơi theo quy định
                if wf_idx < self.total_workflows and not self._stop_requested:
                    if self.delay_between_workflows > 0:
                        self.log(f"Đã hoàn thành các Circle. Bắt đầu nghỉ ngơi {self.delay_between_workflows}s theo quy định...")
                        total_secs = int(self.delay_between_workflows)
                        if total_secs >= 1:
                            for rem in range(total_secs, 0, -1):
                                await self._check_pause_or_stop()
                                self.update_ui_checklist(tasks=f"Nghỉ ({rem}s)")
                                await asyncio.sleep(1)
                        rem_fraction = self.delay_between_workflows - total_secs
                        if rem_fraction > 0:
                            await asyncio.sleep(rem_fraction)

                    self.log("Hết thời gian nghỉ ngơi -> Chuẩn bị cho workflow tiếp theo: Yêu cầu tạo email mới...")
                    await self._check_pause_or_stop()

                    new_email_addr = ""
                    for email_retry in range(1, 5):
                        try:
                            new_email_addr = await create_next_email(self.email_page)
                            if new_email_addr and "@" in new_email_addr:
                                break
                        except Exception as em_err:
                            self.log(f"Cảnh báo: Lỗi khi tạo email mới (lần {email_retry}/4): {em_err}")

                        self.log(f"Chưa lấy được email mới hoặc quá thời gian. Đang thử tải lại trang email (lần {email_retry}/4)...")
                        try:
                            if self.email_page.is_closed():
                                self.email_page = await self.context.new_page()
                            await self.email_page.goto(TEMP_MAIL_NEW_URL, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(1)
                            new_email_addr = await get_current_email(self.email_page, timeout=8000)
                            if new_email_addr and "@" in new_email_addr:
                                break
                        except Exception:
                            try:
                                await self.email_page.goto(TEMP_MAIL_URL, wait_until="domcontentloaded", timeout=15000)
                            except Exception:
                                pass
                        await asyncio.sleep(2)

                    # Phương án dự phòng cao nhất: nếu tab email bị nghẽn, mở lại tab mới
                    if not new_email_addr or "@" not in new_email_addr:
                        self.log("Cảnh báo: Tab email cũ không phản hồi, đang mở lại Tab Email mới...")
                        try:
                            if not self.email_page.is_closed():
                                await self.email_page.close()
                        except Exception:
                            pass
                        self.email_page = await self.context.new_page()
                        await self.email_page.goto(TEMP_MAIL_URL, wait_until="domcontentloaded", timeout=30000)
                        new_email_addr = await get_current_email(self.email_page, timeout=15000)

                    current_email = new_email_addr
                    self.log(f"Created email: {current_email}")
                    await asyncio.sleep(1)

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

    async def _run_single_workflow(self, wf_idx: int, email: str) -> bool:
        try:
            # ----------------------------------------------------
            # BƯỚC 4: Mở / Chuyển sang TARGET WEBSITE ở tab thứ hai
            # ----------------------------------------------------
            if not self.target_page or self.target_page.is_closed():
                self.log(f"Mở Target Website ở tab 2: {self.target_url}")
                self.target_page = await self.context.new_page()
                await self.target_page.goto(self.target_url, wait_until="domcontentloaded", timeout=30000)
            else:
                self.log(f"Chuyển sang Tab 2 Target Website: {self.target_url}")
                if "/auth/login" not in self.target_page.url:
                    await self.target_page.goto(self.target_url, wait_until="domcontentloaded", timeout=30000)

            await self._check_pause_or_stop()

            # ----------------------------------------------------
            # BƯỚC 5: Điền email và nhấn "Gửi mã"
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
            # BƯỚC 6: Quay lại tab temporary email
            # ----------------------------------------------------
            self.log("Chuyển quyền điều khiển về Tab Email tạm thời...")

            # Kiểm tra đảm bảo email trên Tab 2 UCircle trùng khớp 100% với email Tab 1
            if self.target_page and not self.target_page.is_closed():
                await ensure_matching_email_on_target(self.target_page, email, log_cb=self.log)

            # ----------------------------------------------------
            # BƯỚC 7: Vòng lặp chờ OTP
            # QUAN TRỌNG: Chỉ reload email_page!
            # KHÔNG reload target_page!
            # ----------------------------------------------------
            self.update_ui_checklist(waiting_email="⟳")
            otp_found = None
            refresh_count = 0
            has_resent = False
            start_wait_time = time.time()

            while time.time() - start_wait_time < self.otp_timeout:
                await self._check_pause_or_stop()

                # Đồng bộ địa chỉ email giữa Tab 1 và Tab 2
                try:
                    current_tab1_email = await get_current_email(self.email_page, timeout=5000)
                    if current_tab1_email and "@" in current_tab1_email and current_tab1_email.lower() != email.lower():
                        self.log(f"⚠️ Phát hiện Tab 1 đổi sang email mới: {current_tab1_email} (cũ: {email})")
                        email = current_tab1_email
                        self.update_ui_progress(email=email)
                except Exception:
                    pass

                # Nếu UCircle khác email -> Tự động bấm 'Đổi email', nhập lại chuẩn và gửi lại mã
                if self.target_page and not self.target_page.is_closed():
                    fixed = await ensure_matching_email_on_target(self.target_page, email, log_cb=self.log)
                    if fixed:
                        start_wait_time = time.time()
                        refresh_count = 0
                        has_resent = False

                await asyncio.sleep(self.refresh_interval)

                refresh_count += 1
                self.update_ui_checklist(refresh_count=refresh_count)
                self.log(f"Refresh inbox #{refresh_count}")

                # Tự động F5 / Nút Reload của Google Chrome (không bấm link 'Làm mới trang này' trên web)
                try:
                    if "readmail" in self.email_page.url or "error-due" in self.email_page.url:
                        await self.email_page.goto(TEMP_MAIL_URL, wait_until="domcontentloaded", timeout=15000)
                    else:
                        # Gọi trực tiếp lệnh Reload của Google Chrome (Page.reload) tương đương phím F5
                        await self.email_page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception as e:
                    self.log(f"Cảnh báo F5/reload email_page: {e}")

                try:
                    await self.email_page.wait_for_selector(INBOX_TABLE_SELECTOR, timeout=10000)
                except Exception:
                    pass

                # Kiểm tra thư đến
                messages = await get_messages(self.email_page)
                verification_email = find_verification_email(messages)

                # Trường hợp test với Mock Server
                if not verification_email and "127.0.0.1:5000" in self.target_url:
                    from mock_server import MOCK_OTP_STORAGE
                    mock_otp = MOCK_OTP_STORAGE.get(email)
                    if mock_otp and refresh_count >= 2:
                        self.log("Email found (từ Mock Server)")
                        otp_found = mock_otp
                        self.log(f"OTP extracted: {otp_found}")
                        self.update_ui_checklist(waiting_email="✓", otp=otp_found)
                        break

                if verification_email:
                    self.log("Email found")
                    self.update_ui_checklist(waiting_email="✓")

                    # Mở thư và trích xuất OTP
                    otp_found = await extract_otp(self.email_page, verification_email)
                    if otp_found:
                        self.log(f"OTP extracted: {otp_found}")
                        self.update_ui_checklist(otp=otp_found)
                        break
                    else:
                        self.log("Đã tìm thấy thư nhưng đang chờ giải mã hoặc render OTP, sẽ refresh lại...")

                # NẾU ĐÃ RELOAD 2-3 LẦN MÀ CHƯA CÓ MÃ -> BẤM "GỬI LẠI MÃ" TRÊN UCIRCLE
                # Tránh bấm ngay từ đầu gây lỗi rate-limit: "Chưa gửi được mã. Vui lòng thử lại sau giây lát."
                if not verification_email and refresh_count >= 3 and not has_resent:
                    if self.target_page and not self.target_page.is_closed():
                        self.log("Đã reload 3 lần nhưng chưa có email -> Bấm 'Gửi lại mã' trên Target Page...")
                        resent = await resend_code_if_available(self.target_page)
                        if resent:
                            has_resent = True
                            self.log("✓ Đã bấm 'Gửi lại mã' thành công trên UCircle!")
                        else:
                            self.log("Nút 'Gửi lại mã' đang trong thời gian chờ (cooldown), sẽ kiểm tra lại ở lượt refresh sau...")

            if not otp_found:
                self.log(f"Timeout {self.otp_timeout}s: Không nhận được mã OTP!")
                return False

            await self._check_pause_or_stop()

            # ----------------------------------------------------
            # BƯỚC 8: Chuyển về target_page để điền OTP & xác minh
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
            # BƯỚC 9: Bấm "Vào UCircle" & Hoàn thiện hồ sơ Onboarding
            # (Tên hiển thị, @username, Cho tìm, Lưu & bắt đầu, Bỏ qua nơi cư trú)
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
            # BƯỚC 10: Theo dõi và Tham gia danh sách Circle
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
            # BƯỚC 11: Đăng xuất UCircle, KHÔNG out luôn tab đó, chuyển qua tab email làm luồng tiếp theo
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
            # Đảm bảo phiên UCircle luôn được đăng xuất và dọn dẹp sạch sẽ
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
            if self.email_page and not self.email_page.is_closed():
                await self.email_page.close()
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
