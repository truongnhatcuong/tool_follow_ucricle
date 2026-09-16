"""
Module email_service.py
Quản lý mọi tương tác với dịch vụ email tạm thời (10minutemail.net):
- Lấy email hiện tại
- Tạo email tiếp theo (create_next_email)
- Lấy danh sách thư đến
- Tìm thư xác thực
- Trích xuất OTP từ nội dung thư (hỗ trợ chờ vượt Cloudflare)
"""

import asyncio
import re
import logging
from typing import List, Dict, Optional, Any
from playwright.async_api import Page

from selectors import (
    TEMP_MAIL_URL,
    TEMP_MAIL_NEW_URL,
    EMAIL_INPUT_SELECTOR,
    NEW_EMAIL_BUTTON_SELECTOR,
    INBOX_TABLE_SELECTOR,
    INBOX_ROWS_SELECTOR,
    INBOX_ROW_LINK_SELECTOR,
    INBOX_ROW_SENDER_SELECTOR,
    INBOX_ROW_SUBJECT_SELECTOR,
    INBOX_ROW_TIME_SELECTOR,
    EMAIL_CONTENT_CONTAINERS,
    SYSTEM_WELCOME_EMAIL_KEYWORD,
    SYSTEM_SENDER_KEYWORD,
)

logger = logging.getLogger("EmailService")


async def get_current_email(email_page: Page, timeout: int = 15000) -> str:
    """
    Lấy địa chỉ email hiện tại từ ô input giao diện.
    """
    if "error-due" in email_page.url:
        logger.warning("Email tạm đã hết hạn (error-due) -> Đang yêu cầu cấp email mới...")
        await email_page.goto(TEMP_MAIL_NEW_URL, wait_until="domcontentloaded")

    await email_page.wait_for_selector(EMAIL_INPUT_SELECTOR, timeout=timeout)
    for _ in range(25):
        email_val = await email_page.input_value(EMAIL_INPUT_SELECTOR)
        if email_val and "@" in email_val:
            return email_val.strip()
        await asyncio.sleep(0.3)
    return ""


async def create_next_email(email_page: Page, timeout: int = 25000) -> str:
    """
    Yêu cầu tạo email tạm tiếp theo cho workflow mới.
    Bấm vào nút New Email, đợi trang tải lại và địa chỉ email thay đổi.
    """
    old_email = ""
    try:
        old_email = await email_page.input_value(EMAIL_INPUT_SELECTOR)
    except Exception:
        pass

    logger.info(f"Yêu cầu tạo email mới (email cũ: {old_email})")

    # Bấm nút New Email hoặc điều hướng trực tiếp đến new.html
    new_btn = await email_page.query_selector(NEW_EMAIL_BUTTON_SELECTOR)
    if new_btn:
        try:
            await new_btn.click()
        except Exception:
            await email_page.goto(TEMP_MAIL_NEW_URL, wait_until="domcontentloaded")
    else:
        await email_page.goto(TEMP_MAIL_NEW_URL, wait_until="domcontentloaded")

    await email_page.wait_for_selector(EMAIL_INPUT_SELECTOR, timeout=timeout)

    # Vòng lặp chờ email mới khác với email cũ
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < (timeout / 1000.0):
        new_email = await email_page.input_value(EMAIL_INPUT_SELECTOR)
        if new_email and "@" in new_email and new_email != old_email:
            logger.info(f"Đã tạo email mới thành công: {new_email}")
            return new_email.strip()
        await asyncio.sleep(0.5)

    return await email_page.input_value(EMAIL_INPUT_SELECTOR)


async def get_messages(email_page: Page) -> List[Dict[str, Any]]:
    """
    Đọc danh sách các thư hiện có trong Inbox table (#maillist).
    """
    try:
        table = await email_page.query_selector(INBOX_TABLE_SELECTOR)
        if not table:
            return []

        rows = await email_page.query_selector_all(INBOX_ROWS_SELECTOR)
        messages = []

        for row in rows:
            sender_el = await row.query_selector(INBOX_ROW_SENDER_SELECTOR)
            subject_el = await row.query_selector(INBOX_ROW_SUBJECT_SELECTOR)
            time_el = await row.query_selector(INBOX_ROW_TIME_SELECTOR)
            link_el = await row.query_selector(INBOX_ROW_LINK_SELECTOR)

            if not sender_el or not subject_el:
                continue

            sender_text = (await sender_el.inner_text()).strip()
            subject_text = (await subject_el.inner_text()).strip()
            time_text = (await time_el.inner_text()).strip() if time_el else ""
            href = (await link_el.get_attribute("href")) if link_el else ""

            messages.append({
                "sender": sender_text,
                "subject": subject_text,
                "time": time_text,
                "href": href,
                "element": row,
                "link_el": link_el
            })

        return messages
    except Exception as e:
        logger.warning(f"Lỗi khi đọc messages: {e}")
        return []


def find_verification_email(messages: List[Dict[str, Any]], ignored_hrefs: Optional[set] = None) -> Optional[Dict[str, Any]]:
    """
    Tìm thư xác nhận / OTP trong danh sách thư:
    - Bỏ qua thư chào mừng mặc định
    - Bỏ qua các thư đã xử lý
    """
    if not messages:
        return None

    if ignored_hrefs is None:
        ignored_hrefs = set()

    candidates = []
    for msg in messages:
        href = msg.get("href", "")
        sender = msg.get("sender", "").lower()
        subject = msg.get("subject", "").lower()

        # Bỏ qua thư mặc định của 10minutemail
        if SYSTEM_WELCOME_EMAIL_KEYWORD in href or SYSTEM_SENDER_KEYWORD in sender:
            continue
        if "chào mừng tới email 10 phút" in subject:
            continue
        if href in ignored_hrefs:
            continue

        candidates.append(msg)

    if not candidates:
        return None

    # Tìm kiếm thư có từ khóa liên quan đến OTP / UCircle
    keywords = ["ucircle", "otp", "code", "mã", "xác minh", "xác thực", "verify", "verification", "login", "đăng nhập"]
    for msg in candidates:
        subject = msg.get("subject", "").lower()
        sender = msg.get("sender", "").lower()
        if any(kw in subject or kw in sender for kw in keywords):
            return msg

    return candidates[0]


async def extract_otp(email_page: Page, target_msg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Mở thư xem chi tiết, chờ vượt Cloudflare Turnstile và trích xuất mã OTP.
    """
    try:
        # Nếu có target_msg và có link, bấm vào xem thư
        if target_msg and target_msg.get("link_el"):
            link_el = target_msg["link_el"]
            try:
                await link_el.click()
                try:
                    await email_page.wait_for_load_state("domcontentloaded", timeout=4000)
                except Exception:
                    pass
            except Exception:
                href = target_msg.get("href")
                if href:
                    full_url = href if href.startswith("http") else f"https://10minutemail.net/{href}"
                    try:
                        await email_page.goto(full_url, wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        pass

        # Đợi trang đọc thư tải hoàn tất hoặc đợi vượt Cloudflare Turnstile
        for _ in range(15):
            try:
                title = await email_page.title()
                if "Chờ một chút" not in title and "Just a moment" not in title:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        # Chờ và đọc nội dung thư (thử trong tối đa 12 giây để đảm bảo text đã render)
        for attempt in range(12):
            full_text = ""
            try:
                if "error-due" in email_page.url:
                    logger.warning("Phát hiện 10minutemail bị error-due -> Quay lại hòm thư...")
                    await email_page.goto(TEMP_MAIL_URL, wait_until="domcontentloaded", timeout=15000)
                    return None

                for selector in EMAIL_CONTENT_CONTAINERS:
                    try:
                        el = await email_page.query_selector(selector)
                        if el:
                            txt = await el.inner_text()
                            if txt and len(txt.strip()) > 0:
                                full_text += "\n" + txt
                    except Exception:
                        pass

                if not full_text.strip():
                    try:
                        full_text = await email_page.inner_text("body")
                    except Exception:
                        pass
            except Exception as read_err:
                logger.debug(f"Đang chờ nội dung thư ổn định: {read_err}")
                await asyncio.sleep(1)
                continue

            if full_text.strip():
                # 1. Mẫu OTP có từ khóa chỉ dẫn
                pattern_strict = [
                    r'(?:mã|otp|code|mã xác minh|mã xác thực|verification code)[\s:=#\-]+([0-9]{4,8})\b',
                    r'\b([0-9]{4,8})[\s]+(?:là mã|is your code|is your otp|để đăng nhập|để xác minh)',
                ]
                for p in pattern_strict:
                    match = re.search(p, full_text, re.IGNORECASE)
                    if match:
                        otp = match.group(1)
                        logger.info(f"Tìm thấy OTP theo mẫu từ khóa: {otp}")
                        return otp

                # 2. Mẫu 6 chữ số phổ biến
                six_digit_match = re.search(r'\b([0-9]{6})\b', full_text)
                if six_digit_match:
                    otp = six_digit_match.group(1)
                    logger.info(f"Tìm thấy OTP 6 chữ số: {otp}")
                    return otp

                # 3. Mẫu 4 chữ số
                four_digit_match = re.search(r'\b([0-9]{4})\b', full_text)
                if four_digit_match:
                    otp = four_digit_match.group(1)
                    logger.info(f"Tìm thấy OTP 4 chữ số: {otp}")
                    return otp

            await asyncio.sleep(1)

        return None
    except Exception as e:
        logger.error(f"Lỗi khi trích xuất OTP: {e}")
        return None
