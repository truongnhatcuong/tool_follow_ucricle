"""
Module target_service.py
Quản lý mọi thao tác trên trang web đích (Target Website - UCircle):
- Điền email và nhấn "Gửi mã đăng nhập"
- Hỗ trợ nhấn "Gửi lại mã" (Resend OTP) khi cần
- Điền OTP và bấm "Xác minh & đăng nhập"
- Xử lý nút "Vào UCircle"
- Tự động hoàn thiện hồ sơ người dùng (Tên hiển thị, @username, Cho tìm, Lưu & bắt đầu)
- Đóng tab target_page và làm mới session cho workflow tiếp theo
"""

import asyncio
import re
import random
import logging
from typing import Optional, Dict, Tuple, Any
from playwright.async_api import Page, BrowserContext

from selectors import (
    DEFAULT_TARGET_URL,
    TARGET_EMAIL_INPUT_SELECTOR,
    TARGET_SEND_CODE_BUTTON_SELECTOR,
    TARGET_RESEND_BUTTON_SELECTOR,
    TARGET_OTP_INPUT_SELECTOR,
    TARGET_SUBMIT_BUTTON_SELECTOR,
    TARGET_SUCCESS_SELECTOR,
    TARGET_ENTER_APP_BUTTON_SELECTOR,
    ONBOARDING_DIALOG_SELECTOR,
    ONBOARDING_NAME_INPUT_SELECTOR,
    ONBOARDING_USERNAME_INPUT_SELECTOR,
    ONBOARDING_HANDLE_ERROR_SELECTOR,
    ONBOARDING_DISCOVERABLE_YES_SELECTOR,
    ONBOARDING_SAVE_BUTTON_SELECTOR,
    ONBOARDING_RESIDENCE_SKIP_BUTTON_SELECTOR,
    CIRCLE_CTA_CONTAINER_SELECTOR,
    CIRCLE_FOLLOW_BUTTON_SELECTOR,
    CIRCLE_JOIN_BUTTON_SELECTOR,
    TARGET_LOGOUT_BUTTON_SELECTOR,
    TARGET_CHANGE_EMAIL_BUTTON_SELECTOR,
)

logger = logging.getLogger("TargetService")

# Danh sách tên tiếng Việt tự nhiên phong phú
SAMPLE_VIETNAMESE_NAMES = [
    "Minh Anh", "Tuấn Kiệt", "Quốc Bảo", "Phương Linh", "Hải Đăng",
    "Khánh Vy", "Bảo Trâm", "Đức Huy", "Gia Hưng", "Thanh Trúc",
    "Hoàng Nam", "Thùy Dung", "Nhật Minh", "Thảo My", "Anh Tuấn",
    "Mai Anh", "Ngọc Hân", "Bảo Long", "Hồng Ngọc", "Văn Hùng"
]


def generate_profile_data(email: str) -> Tuple[str, str]:
    """
    Sinh tên hiển thị và @username hợp lệ:
    - Tên hiển thị: Tên tự nhiên đẹp
    - @username: 3-32 ký tự chữ thường, số, gạch dưới
    """
    display_name = random.choice(SAMPLE_VIETNAMESE_NAMES)
    
    # Lấy tiền tố email làm cơ sở cho username
    email_prefix = email.split("@")[0].lower() if "@" in email else "user"
    clean_prefix = re.sub(r'[^a-z0-9_]', '', email_prefix)
    if not clean_prefix or len(clean_prefix) < 3:
        clean_prefix = f"user_{clean_prefix}"
        
    random_suffix = random.randint(10, 999)
    username = f"{clean_prefix[:24]}_{random_suffix}"
    
    return display_name, username


async def get_displayed_email_on_target(target_page: Page) -> Optional[str]:
    """
    Lấy địa chỉ email đang được hiển thị trên màn hình OTP của Target Website (UCircle).
    """
    try:
        # Cách 1: Tìm trong phần tử cha gần nút "Đổi email" nhất
        change_btn = await target_page.query_selector(TARGET_CHANGE_EMAIL_BUTTON_SELECTOR)
        if change_btn:
            parent_text = await change_btn.evaluate(
                "el => el.closest('div, form, p, section')?.innerText || el.parentElement?.innerText || ''"
            )
            matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', parent_text)
            if matches:
                return matches[0].strip().lower()

        # Cách 2: Quét toàn bộ text trong body
        body_text = await target_page.inner_text("body")
        matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', body_text)
        if matches:
            return matches[0].strip().lower()
    except Exception as e:
        logger.debug(f"Không thể đọc email hiển thị trên target page: {e}")
    return None


async def ensure_matching_email_on_target(
    target_page: Optional[Page],
    expected_email: str,
    log_cb: Optional[Any] = None
) -> bool:
    """
    Kiểm tra xem email trên UCircle có khớp với expected_email (từ 10minutemail) không.
    Nếu đang ở màn hình OTP mà email hiển thị khác expected_email:
    - Bấm nút 'Đổi email'
    - Điền lại chuẩn xác expected_email
    - Bấm 'Gửi mã đăng nhập'
    - Chờ quay lại màn hình OTP
    Trả về True nếu đã đổi email thành công, False nếu email đã trùng khớp hoặc không cần đổi.
    """
    if not target_page or target_page.is_closed():
        return False

    expected_clean = expected_email.strip().lower()
    if not expected_clean or "@" not in expected_clean:
        return False

    try:
        # Kiểm tra sự xuất hiện của nút "Đổi email" trên màn hình OTP
        change_btn = await target_page.query_selector(TARGET_CHANGE_EMAIL_BUTTON_SELECTOR)
        if not change_btn or not await change_btn.is_visible():
            return False

        # Lấy email hiện đang hiển thị trên UCircle
        displayed_email = await get_displayed_email_on_target(target_page)
        
        # Nếu UCircle đã hiển thị đúng email mong đợi -> Khớp 100%, không cần đổi
        if displayed_email and displayed_email == expected_clean:
            return False

        # Kiểm tra thêm trong vùng text xung quanh xem có chứa expected_clean không
        try:
            surrounding_text = await change_btn.evaluate(
                "el => el.closest('div, form, p, section')?.innerText || ''"
            )
            if expected_clean in surrounding_text.lower():
                return False
        except Exception:
            pass

        # PHÁT HIỆN EMAIL KHÁC NHAU:
        warn_msg = f"Phát hiện email trên UCircle ({displayed_email or 'không rõ'}) KHÁC email 10p ({expected_clean})!"
        logger.warning(warn_msg)
        if log_cb:
            log_cb(f"⚠️ {warn_msg}")
            log_cb("Bấm nút 'Đổi email' để nhập lại chuẩn xác email từ 10minutemail...")

        # 1. Bấm nút "Đổi email"
        await change_btn.click()
        await asyncio.sleep(0.5)

        # 2. Chờ ô nhập email xuất hiện
        await target_page.wait_for_selector(TARGET_EMAIL_INPUT_SELECTOR, timeout=8000)

        # 3. Xóa sạch và nhập chuẩn xác expected_email
        await target_page.click(TARGET_EMAIL_INPUT_SELECTOR)
        await target_page.fill(TARGET_EMAIL_INPUT_SELECTOR, "")
        await target_page.fill(TARGET_EMAIL_INPUT_SELECTOR, expected_clean)
        await asyncio.sleep(0.3)

        # 4. Bấm "Gửi mã đăng nhập"
        if log_cb:
            log_cb(f"Bấm 'Gửi mã đăng nhập' cho email đúng: {expected_clean}...")
        await target_page.wait_for_selector(TARGET_SEND_CODE_BUTTON_SELECTOR, timeout=8000)
        await target_page.click(TARGET_SEND_CODE_BUTTON_SELECTOR)

        # 5. Chờ giao diện OTP xuất hiện lại
        await target_page.wait_for_selector(TARGET_OTP_INPUT_SELECTOR, timeout=15000)
        if log_cb:
            log_cb("✓ Đã đổi email và gửi mã OTP thành công tới đúng email 10p!")

        return True

    except Exception as e:
        err_msg = f"Lỗi khi thực hiện Đổi email trên UCircle: {e}"
        logger.error(err_msg)
        if log_cb:
            log_cb(err_msg)
        return False


async def fill_email_and_request_code(
    target_page: Page,
    email: str,
    custom_selectors: Optional[Dict[str, str]] = None
) -> bool:
    """
    Điền email vào form đăng nhập/đăng ký của Target Website và nhấn "Gửi mã đăng nhập".
    """
    email_selector = (custom_selectors or {}).get("email_input") or TARGET_EMAIL_INPUT_SELECTOR
    send_btn_selector = (custom_selectors or {}).get("send_btn") or TARGET_SEND_CODE_BUTTON_SELECTOR
    otp_selector = (custom_selectors or {}).get("otp_input") or TARGET_OTP_INPUT_SELECTOR

    try:
        # Luôn đảm bảo đang ở đúng trang /auth/login
        if "/auth/login" not in target_page.url:
            await target_page.goto(DEFAULT_TARGET_URL, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(0.5)

        # Chờ bất kỳ trạng thái nào xuất hiện (Form email, Đăng xuất, Đổi email, hoặc Vào UCircle)
        for attempt in range(3):
            try:
                await target_page.wait_for_selector(
                    f"{email_selector}, button:has-text('Đăng xuất'), button:has-text('Đổi email'), button:has-text('Vào UCircle')",
                    timeout=5000
                )
            except Exception:
                pass

            # 1. Nếu có nút "Đăng xuất" hoặc màn hình "Bạn đã đăng nhập"
            logout_btn = await target_page.query_selector("button:has-text('Đăng xuất'), button._link_1yt08_137:has-text('Đăng xuất')")
            if logout_btn and await logout_btn.is_visible():
                logger.info("Phát hiện tài khoản cũ còn lưu session ('Đăng xuất') -> Bấm 'Đăng xuất'...")
                await logout_btn.click()
                await asyncio.sleep(1)
                continue

            # 2. Nếu đang ở màn hình OTP
            change_btn = await target_page.query_selector(TARGET_CHANGE_EMAIL_BUTTON_SELECTOR)
            if change_btn and await change_btn.is_visible():
                displayed_email = await get_displayed_email_on_target(target_page)
                if displayed_email and displayed_email == email.strip().lower():
                    logger.info(f"Target page đã ở sẵn màn hình OTP với đúng email: {email}")
                    return True
                logger.info(f"Target page đang kẹt ở màn hình OTP email ({displayed_email}) -> Bấm 'Đổi email'...")
                await change_btn.click()
                await asyncio.sleep(0.6)
                continue

            # 3. Kiểm tra ô nhập email đã sẵn sàng chưa
            email_el = await target_page.query_selector(email_selector)
            if email_el and await email_el.is_visible():
                break

            # Nếu chưa thấy ô nhập email (bị kẹt phiên cũ), xóa sạch storage và tải lại trang
            logger.info("Chưa thấy ô nhập email, làm sạch storage và tải lại /auth/login...")
            try:
                await target_page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e){} }")
            except Exception:
                pass
            await target_page.goto(DEFAULT_TARGET_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)

        logger.info(f"Điền email: {email} vào target page...")
        await target_page.wait_for_selector(email_selector, timeout=10000)
        # Xóa sạch ô nhập email trước khi điền
        await target_page.click(email_selector)
        await target_page.fill(email_selector, "")
        await target_page.fill(email_selector, email.strip())

        await asyncio.sleep(0.3)

        logger.info("Bấm nút 'Gửi mã đăng nhập' trên target page...")
        await target_page.wait_for_selector(send_btn_selector, timeout=10000)
        await target_page.click(send_btn_selector)

        # Chờ giao diện chuyển sang màn hình nhập mã OTP
        logger.info("Chờ màn hình nhập mã OTP xuất hiện...")
        await target_page.wait_for_selector(otp_selector, timeout=15000)
        logger.info("Màn hình nhập mã OTP đã hiển thị thành công.")

        return True
    except Exception as e:
        logger.error(f"Lỗi khi gửi mã trên target page: {e}")
        return False



async def resend_code_if_available(target_page: Page) -> bool:
    """
    Bấm nút 'Gửi lại mã' nếu nút này hiển thị và sẵn sàng để kích hoạt gửi email.
    """
    try:
        resend_btn = await target_page.query_selector(TARGET_RESEND_BUTTON_SELECTOR)
        if resend_btn and await resend_btn.is_visible():
            btn_text = (await resend_btn.inner_text()).strip()
            if "gửi lại" not in btn_text.lower():
                logger.warning(f"Nút tìm thấy không phải 'Gửi lại mã' (text='{btn_text}') -> bỏ qua.")
                return False

            is_disabled = await resend_btn.is_disabled()
            if not is_disabled:
                logger.info(f"Phát hiện nút '{btn_text}' -> Tiến hành bấm để nhận OTP nhanh hơn...")
                await resend_btn.click()
                await asyncio.sleep(1)

                # Kiểm tra thông báo lỗi cooldown ("Chưa gửi được mã...") do server trả về
                try:
                    body_text = (await target_page.inner_text("body")).lower()
                    if "chưa gửi được mã" in body_text or "thử lại sau" in body_text:
                        logger.warning("Server báo cooldown khi bấm 'Gửi lại mã', sẽ thử lại ở lượt sau.")
                        return False
                except Exception:
                    pass

                return True
        return False
    except Exception as e:
        logger.warning(f"Không thể bấm 'Gửi lại mã': {e}")
        return False


async def fill_otp_and_verify(
    target_page: Page,
    otp: str,
    custom_selectors: Optional[Dict[str, str]] = None,
    timeout: int = 15000
) -> bool:
    """
    Nhập mã OTP vào target_page, bấm xác minh và đợi trạng thái thành công.
    """
    otp_selector = (custom_selectors or {}).get("otp_input") or TARGET_OTP_INPUT_SELECTOR
    submit_selector = (custom_selectors or {}).get("submit_btn") or TARGET_SUBMIT_BUTTON_SELECTOR
    success_selector = (custom_selectors or {}).get("success_selector") or TARGET_SUCCESS_SELECTOR

    try:
        logger.info(f"Nhập mã OTP: {otp} vào target page...")
        await target_page.wait_for_selector(otp_selector, timeout=timeout)
        
        # Nhập mã OTP (kết hợp cả fill và press_sequentially để kích hoạt sự kiện input/onChange trên React)
        otp_locator = target_page.locator(otp_selector)
        await otp_locator.fill("")
        await otp_locator.press_sequentially(otp, delay=40)

        await asyncio.sleep(0.6)

        # Kiểm tra nút submit ("Xác minh & đăng nhập")
        submit_btn = await target_page.query_selector(submit_selector)
        if submit_btn and await submit_btn.is_visible():
            is_disabled = await submit_btn.is_disabled()
            if not is_disabled:
                logger.info("Bấm nút 'Xác minh & đăng nhập'...")
                await submit_btn.click()

        # Đợi màn hình đăng nhập thành công
        logger.info("Chờ thông báo đăng nhập thành công...")
        try:
            await target_page.wait_for_selector(success_selector, timeout=timeout)
            logger.info("Đã phát hiện trạng thái đăng nhập thành công!")
            return True
        except Exception:
            # Kiểm tra URL hoặc nội dung trang
            current_url = target_page.url
            if "/app" in current_url:
                return True
            body_text = (await target_page.inner_text("body")).lower()
            if any(k in body_text for k in ["bạn đã đăng nhập", "vào ucircle", "tạo hồ sơ", "thành công"]):
                return True

            logger.warning("Chưa xác nhận được trạng thái đăng nhập sau khi nhập OTP")
            return False
    except Exception as e:
        logger.error(f"Lỗi khi xác minh OTP trên target page: {e}")
        return False


async def enter_app_and_complete_profile(
    target_page: Page,
    email: str,
    ai_model_instance: Optional[Any] = None,
    timeout: int = 15000
) -> bool:
    """
    Xử lý sau khi đăng nhập:
    1. Bấm nút "Vào UCircle"
    2. Điền tên hiển thị và @username (sử dụng AI nếu có, tự động tránh trùng username)
    3. Chọn "Cho tìm"
    4. Bấm "Lưu & bắt đầu"
    5. Bấm "Bỏ qua" nơi cư trú để vào trang chủ
    """
    try:
        # 1. Bấm nút "Vào UCircle" nếu có
        enter_btn = await target_page.query_selector(TARGET_ENTER_APP_BUTTON_SELECTOR)
        if enter_btn and await enter_btn.is_visible():
            logger.info("Bấm nút 'Vào UCircle'...")
            await enter_btn.click()
            await asyncio.sleep(1.5)

        # 2. Kiểm tra xem có hộp thoại Tạo hồ sơ (Onboarding Gate) hay không
        try:
            await target_page.wait_for_selector(ONBOARDING_NAME_INPUT_SELECTOR, timeout=6000)
        except Exception:
            pass

        name_input = await target_page.query_selector(ONBOARDING_NAME_INPUT_SELECTOR)
        username_input = await target_page.query_selector(ONBOARDING_USERNAME_INPUT_SELECTOR)

        if name_input and username_input:
            if ai_model_instance:
                profile = ai_model_instance.generate_profile(email)
                display_name = profile.get("name") or "Minh Anh"
                username = profile.get("username") or f"user_{random.randint(1000, 9999)}"
            else:
                display_name, username = generate_profile_data(email)

            logger.info(f"Điền thông tin hồ sơ: Tên='{display_name}', @username='{username}'")

            # 1. Điền Tên hiển thị
            name_locator = target_page.locator(ONBOARDING_NAME_INPUT_SELECTOR)
            await name_locator.click()
            await name_locator.fill(display_name)
            await asyncio.sleep(0.4)

            # 2. Điền @username
            username_locator = target_page.locator(ONBOARDING_USERNAME_INPUT_SELECTOR)
            await username_locator.click()
            await username_locator.fill("")
            await username_locator.press_sequentially(username, delay=35)
            await asyncio.sleep(0.6)

            # Đảm bảo Tên hiển thị không bị xóa do React re-render
            name_val = await name_locator.input_value()
            if not name_val or not name_val.strip():
                await name_locator.click()
                await name_locator.fill(display_name)
                await asyncio.sleep(0.3)

            # Đảm bảo @username không bị xóa
            user_val = await username_locator.input_value()
            if not user_val or not user_val.strip():
                await username_locator.click()
                await username_locator.press_sequentially(username, delay=35)
                await asyncio.sleep(0.5)

            # 3. Kiểm tra lỗi trùng username và thử lại nếu cần
            for retry in range(1, 6):
                # Chờ để UCircle kiểm tra username (debounce / api check)
                await asyncio.sleep(0.8)
                err_el = await target_page.query_selector(ONBOARDING_HANDLE_ERROR_SELECTOR)
                has_duplicate_error = False
                if err_el and await err_el.is_visible():
                    err_txt = (await err_el.inner_text()).strip()
                    if err_txt and any(k in err_txt.lower() for k in ["đã có", "chọn tên khác", "tồn tại", "already"]):
                        has_duplicate_error = True

                if not has_duplicate_error:
                    logger.info(f"✓ @username '{username}' hợp lệ và không bị trùng!")
                    break

                # Sinh username thay thế
                if ai_model_instance:
                    username = ai_model_instance.generate_alternative_username(username)
                else:
                    clean_pre = re.sub(r'[^a-z0-9_]', '', username.split('_')[0])
                    username = f"{clean_pre}_{random.randint(10000, 999999)}"

                logger.warning(f"Phát hiện @username bị trùng -> Đổi sang: '{username}' (thử lại {retry}/5)")
                await username_locator.click()
                await username_locator.fill("")
                await username_locator.press_sequentially(username, delay=35)
                await asyncio.sleep(0.5)

            # 4. Chọn "Cho tìm" (Cho người khác tìm thấy bạn?)
            opt_yes = await target_page.query_selector(ONBOARDING_DISCOVERABLE_YES_SELECTOR)
            if opt_yes and await opt_yes.is_visible():
                logger.info("Chọn tùy chọn 'Cho tìm'...")
                await opt_yes.click()
                await asyncio.sleep(0.4)

            # 5. Đợi nút "Lưu & bắt đầu" sẵn sàng (enabled) và bấm
            save_btn = await target_page.query_selector(ONBOARDING_SAVE_BUTTON_SELECTOR)
            if save_btn:
                logger.info("Chờ nút 'Lưu & bắt đầu' kích hoạt...")
                for _ in range(20):
                    if not await save_btn.is_disabled():
                        break
                    await asyncio.sleep(0.3)

                logger.info("Bấm nút 'Lưu & bắt đầu'...")
                await save_btn.click()
                await asyncio.sleep(2)

                # 6. Xử lý bước kế tiếp: Bấm nút "Bỏ qua" nơi cư trú để vào thẳng trang chủ
                try:
                    logger.info("Chờ nút 'Bỏ qua' nơi cư trú...")
                    skip_btn = await target_page.wait_for_selector(
                        ONBOARDING_RESIDENCE_SKIP_BUTTON_SELECTOR,
                        timeout=8000
                    )
                    if skip_btn and await skip_btn.is_visible():
                        logger.info("Phát hiện bước chọn nơi cư trú -> Bấm nút 'Bỏ qua'...")
                        await skip_btn.click()
                        await asyncio.sleep(1.5)
                except Exception:
                    logger.info("Không phát hiện nút 'Bỏ qua' nơi cư trú, có thể đã chuyển trang.")

                logger.info("✓ Hoàn thành tạo hồ sơ UCircle và vào trang chủ thành công!")
        else:
            logger.info("Không phát hiện hộp thoại tạo hồ sơ (có thể tài khoản đã có hồ sơ từ trước hoặc đã vào trang chủ).")

        return True
    except Exception as e:
        logger.error(f"Lỗi khi hoàn thiện hồ sơ UCircle: {e}")
        return False


async def process_circles(
    target_page: Page,
    circle_urls: list,
    delay_between_circles: float = 1,
    log_cb: Optional[Any] = None
) -> int:
    """
    Duyệt danh sách Circle URLs:
    - Mở từng Circle
    - Bấm 'Theo dõi' trước
    - Bấm '＋ Tham gia' sau
    - Nghỉ ngơi giữa các Circle (tối ưu hóa tốc độ cao)
    """
    if not circle_urls:
        return 0

    success_count = 0
    total = len(circle_urls)

    for idx, raw_url in enumerate(circle_urls, 1):
        url = raw_url.strip()
        if not url:
            continue

        prefix_log = f"Circle [{idx}/{total}]"
        try:
            if log_cb:
                log_cb(f"{prefix_log}: Điều hướng tới {url}...")

            await target_page.goto(url, wait_until="domcontentloaded", timeout=25000)

            # Chờ nhanh nút Theo dõi hoặc Tham gia hiển thị (không sleep tĩnh lâu)
            try:
                await target_page.wait_for_selector(
                    f"{CIRCLE_FOLLOW_BUTTON_SELECTOR}, {CIRCLE_JOIN_BUTTON_SELECTOR}, {CIRCLE_CTA_CONTAINER_SELECTOR}",
                    state="visible",
                    timeout=3500
                )
            except Exception:
                pass

            # Đệm ngắn đảm bảo DOM đã gắn event handler
            await asyncio.sleep(0.3)

            # BƯỚC A: Bấm "Theo dõi" trước
            follow_btn = await target_page.query_selector(CIRCLE_FOLLOW_BUTTON_SELECTOR)
            if follow_btn and await follow_btn.is_visible():
                is_following = await follow_btn.get_attribute("data-following")
                aria_pressed = await follow_btn.get_attribute("aria-pressed")
                btn_text = (await follow_btn.inner_text()).strip().lower()
                
                if is_following != "true" and aria_pressed != "true" and "đang theo dõi" not in btn_text:
                    if log_cb:
                        log_cb(f"{prefix_log}: Bấm 'Theo dõi'...")
                    await follow_btn.click()
                    await asyncio.sleep(0.35)
                    if log_cb:
                        log_cb(f"{prefix_log}: ✓ Đã theo dõi thành công")
                else:
                    if log_cb:
                        log_cb(f"{prefix_log}: Đã theo dõi từ trước")
            else:
                if log_cb:
                    log_cb(f"{prefix_log}: Không tìm thấy nút 'Theo dõi' hoặc đã theo dõi")

            # BƯỚC B: Bấm "＋ Tham gia" sau
            join_btn = await target_page.query_selector(CIRCLE_JOIN_BUTTON_SELECTOR)
            if join_btn and await join_btn.is_visible():
                if log_cb:
                    log_cb(f"{prefix_log}: Bấm '＋ Tham gia'...")
                await join_btn.click()
                await asyncio.sleep(0.4)

                # Kiểm tra nhanh xem có popup/dialog xác nhận tham gia hay không
                try:
                    confirm_btn = await target_page.query_selector(
                        "button[data-join-confirm='true'], div[role='dialog'] button:has-text('Tham gia'), div[role='dialog'] button:has-text('Xác nhận')"
                    )
                    if confirm_btn and await confirm_btn.is_visible():
                        await confirm_btn.click()
                        await asyncio.sleep(0.3)
                except Exception:
                    pass

                if log_cb:
                    log_cb(f"{prefix_log}: ✓ Đã tham gia thành công")
            else:
                if log_cb:
                    log_cb(f"{prefix_log}: Không tìm thấy nút '＋ Tham gia' (có thể đã là thành viên)")

            success_count += 1

            if idx < total and delay_between_circles > 0:
                await asyncio.sleep(delay_between_circles)

        except Exception as e:
            err_msg = f"{prefix_log}: Lỗi khi xử lý Circle {url}: {e}"
            logger.error(err_msg)
            if log_cb:
                log_cb(err_msg)

    return success_count



async def logout_and_prepare_next_target_session(
    target_page: Optional[Page],
    context: BrowserContext,
    target_url: str = DEFAULT_TARGET_URL
) -> Optional[Page]:
    """
    Sau khi workflow hoàn tất (duyệt xong các Circle):
    - Chuyển về trang auth/login (nếu đang ở trang Circle)
    - Bấm nút "Đăng xuất" trên UCircle
    - Xóa localStorage, sessionStorage và cookies phiên
    - KHÔNG tắt (close/out) tab target_page, giữ nguyên tab ở màn hình đăng nhập sẵn sàng cho workflow kế tiếp
    """
    if not target_page or target_page.is_closed():
        return None

    try:
        logger.info("Chuyển về trang đăng nhập UCircle để đăng xuất...")
        if "/auth/login" not in target_page.url:
            await target_page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)

        # 1. Tìm và bấm nút "Đăng xuất"
        for _ in range(5):
            logout_btn = await target_page.query_selector(TARGET_LOGOUT_BUTTON_SELECTOR)
            if logout_btn and await logout_btn.is_visible():
                logger.info("Bấm nút 'Đăng xuất' trên UCircle...")
                await logout_btn.click()
                await asyncio.sleep(1.5)
                break
            await asyncio.sleep(0.5)

        # 2. Xóa localStorage & sessionStorage của trang UCircle
        try:
            await target_page.evaluate("""
                () => {
                    try { localStorage.clear(); } catch(e) {}
                    try { sessionStorage.clear(); } catch(e) {}
                }
            """)
        except Exception:
            pass

        # 3. Xóa cookies target
        try:
            cookies = await context.cookies()
            cookies_to_clear = [c for c in cookies if "10minutemail" not in c.get("domain", "")]
            for c in cookies_to_clear:
                try:
                    await context.clear_cookies(name=c["name"], domain=c["domain"])
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Đảm bảo giao diện đã hiển thị ô nhập email sạch
        try:
            if "/auth/login" not in target_page.url:
                await target_page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        logger.info("✓ Đã đăng xuất UCircle và chuẩn bị tab đăng nhập sẵn sàng cho workflow tiếp theo")
        return target_page
    except Exception as e:
        logger.warning(f"Lỗi khi thực hiện đăng xuất UCircle: {e}")
        return target_page


async def reset_target_session(context: BrowserContext, target_page: Optional[Page]) -> None:
    """
    Sau khi workflow hoàn tất:
    - Đóng target_page
    - Reset cookies/session của target website (không ảnh hưởng tới email_page)
    """
    if target_page:
        try:
            target_url = target_page.url
            await target_page.close()
            logger.info(f"Đã đóng target_page: {target_url}")
        except Exception as e:
            logger.warning(f"Lỗi khi đóng target_page: {e}")

    try:
        cookies = await context.cookies()
        # Chỉ xóa cookies của domain target (không xóa cookies 10minutemail)
        cookies_to_clear = [c for c in cookies if "10minutemail" not in c.get("domain", "")]
        for c in cookies_to_clear:
            try:
                await context.clear_cookies(name=c["name"], domain=c["domain"])
            except Exception:
                pass
        logger.info("Đã reset session của target website thành công")
    except Exception as e:
        logger.warning(f"Lỗi khi reset cookies target: {e}")
