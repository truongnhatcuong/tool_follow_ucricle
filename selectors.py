"""
Module selectors.py
Chứa toàn bộ CSS selectors và cấu hình URL cho:
1. Trang email tạm thời (10minutemail.net)
2. Trang web đích (Target Website - Hỗ trợ UCircle & Website tùy biến)
Tuyệt đối không hard-code selector trong business logic.

LƯU Ý KỸ THUẬT:
File này re-export toàn bộ thuộc tính của Python Standard Library 'selectors'
để tránh xung đột shadowing.
"""

import sys
import importlib.util

# -------------------------------------------------------------
# 0. RE-EXPORT PYTHON STANDARD LIBRARY SELECTORS
# -------------------------------------------------------------
try:
    _stdlib_path = None
    for p in sys.path:
        if ("lib" in p.lower() or "python" in p.lower()) and p not in [".", "", sys.path[0]]:
            import os
            candidate = os.path.join(p, "selectors.py")
            if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(__file__):
                _stdlib_path = candidate
                break

    if _stdlib_path:
        _spec = importlib.util.spec_from_file_location("_stdlib_selectors", _stdlib_path)
        _stdlib_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_stdlib_mod)
        for _k, _v in _stdlib_mod.__dict__.items():
            if not _k.startswith("__"):
                globals()[_k] = _v
except Exception:
    pass


# ==========================================
# 1. CẤU HÌNH & SELECTORS CHO 10MINUTEMAIL
# ==========================================

# URL gốc của 10minutemail hỗ trợ tiếng Việt
TEMP_MAIL_URL = "https://10minutemail.net/?lang=vi"
TEMP_MAIL_NEW_URL = "https://10minutemail.net/new.html"

# Ô input hiển thị địa chỉ email hiện tại
EMAIL_INPUT_SELECTOR = "#fe_text"

# Nút copy email
COPY_BUTTON_SELECTOR = "#copy-button"

# Nút tạo email mới / đổi email
NEW_EMAIL_BUTTON_SELECTOR = "a[href*='new.html']"

# Bảng hòm thư đến (Inbox)
INBOX_TABLE_SELECTOR = "#maillist"
INBOX_ROWS_SELECTOR = "#maillist tbody tr"

# Các phần tử trong 1 dòng thư
INBOX_ROW_LINK_SELECTOR = "a"
INBOX_ROW_SENDER_SELECTOR = "td:nth-child(1)"
INBOX_ROW_SUBJECT_SELECTOR = "td:nth-child(2)"
INBOX_ROW_TIME_SELECTOR = "td:nth-child(3)"

# Vùng hiển thị nội dung thư sau khi click xem
EMAIL_CONTENT_CONTAINERS = [
    "#tab1",
    ".tab_container",
    ".mailinfolist",
    "#tab0",
    "div.ui-content"
]

# ID hoặc sender của thư mặc định hệ thống (để bỏ qua khi tìm OTP)
SYSTEM_WELCOME_EMAIL_KEYWORD = "mid=welcome"
SYSTEM_SENDER_KEYWORD = "no-reply@10minutemail.net"


# ==========================================
# 2. CẤU HÌNH & SELECTORS CHO TARGET WEBSITE (UCIRCLE)
# ==========================================

# URL mặc định của trang web đích (UCircle)
DEFAULT_TARGET_URL = "https://ucircle.net/auth/login"

# Ô nhập email đăng nhập/đăng ký
TARGET_EMAIL_INPUT_SELECTOR = "input[type='email'], #email, input[name='email']"

# Nút "Gửi mã đăng nhập" / "Gửi mã" / "Send OTP"
TARGET_SEND_CODE_BUTTON_SELECTOR = (
    "button:has-text('Gửi mã đăng nhập'), button:has-text('Gửi mã'), "
    "#send-otp-btn, button:has-text('Send Code')"
)

TARGET_RESEND_BUTTON_SELECTOR = "button:has-text('Gửi lại mã'), button:has-text('Gửi lại')"

# Nút "Đổi email" trên màn hình OTP của UCircle
TARGET_CHANGE_EMAIL_BUTTON_SELECTOR = (
    "button:has-text('Đổi email'), button._link_1yt08_137:has-text('Đổi email'), "
    "button[class*='_link_']:has-text('Đổi email')"
)


# Ô nhập mã OTP (UCircle dùng #uc-code hoặc placeholder 6 dấu chấm)
TARGET_OTP_INPUT_SELECTOR = (
    "#uc-code, input[placeholder*='••'], input[inputmode='numeric'], "
    "#otp, input[name='otp'], input[name='code']"
)

# Nút "Xác minh & đăng nhập" / "Submit"
TARGET_SUBMIT_BUTTON_SELECTOR = (
    "button:has-text('Xác minh & đăng nhập'), #verify-btn, "
    "button:has-text('Xác minh'), button[type='submit']"
)

# Nhận diện màn hình đăng nhập thành công ("Bạn đã đăng nhập")
TARGET_SUCCESS_SELECTOR = (
    "h1:has-text('Bạn đã đăng nhập'), button:has-text('Vào UCircle'), "
    "input[data-gate-name='true'], .success, #success-msg"
)

# Nút "Vào UCircle" sau khi đăng nhập thành công
TARGET_ENTER_APP_BUTTON_SELECTOR = "button:has-text('Vào UCircle')"

# Nút "Đăng xuất" trên UCircle
TARGET_LOGOUT_BUTTON_SELECTOR = (
    "button:has-text('Đăng xuất'), button._link_1yt08_137, "
    "div._linkRow_1yt08_137 button, button[class*='_link_']"
)

# ==========================================
# 3. SELECTORS CHO ONBOARDING TẠO HỒ SƠ UCIRCLE
# ==========================================

# Hộp thoại tạo hồ sơ
ONBOARDING_DIALOG_SELECTOR = (
    "div[role='dialog'], div[class*='_card_ni6ls_'], "
    "input[data-gate-name='true']"
)

# Ô nhập "Tên hiển thị"
ONBOARDING_NAME_INPUT_SELECTOR = "input[data-gate-name='true']"

# Ô nhập "@username"
ONBOARDING_USERNAME_INPUT_SELECTOR = "input[data-gate-username='true']"

# Báo lỗi khi username bị trùng ("@username này đã có người dùng. Hãy chọn tên khác.")
ONBOARDING_HANDLE_ERROR_SELECTOR = (
    "span[data-gate-handle-error='true'], span:has-text('đã có người dùng'), "
    "span:has-text('Hãy chọn tên khác')"
)

# Nút radio "Cho tìm" (Cho người khác tìm thấy bạn?)
ONBOARDING_DISCOVERABLE_YES_SELECTOR = "button[data-gate-discoverable-opt='yes']"

# Nút "Lưu & bắt đầu"
ONBOARDING_SAVE_BUTTON_SELECTOR = "button[data-gate-save='true'], button:has-text('Lưu & bắt đầu')"

# Nút "Bỏ qua" tại bước nơi cư trú (residence)
ONBOARDING_RESIDENCE_SKIP_BUTTON_SELECTOR = (
    "button[data-gate-residence-skip='true'], button:has-text('Bỏ qua')"
)

# ==========================================
# 4. SELECTORS CHO TRANG CIRCLE (THEO DÕI & THAM GIA)
# ==========================================

# Vùng CTA của Circle
CIRCLE_CTA_CONTAINER_SELECTOR = (
    "div[data-circle-cta='true'], div[class*='_cta_mqun5_']"
)

# Nút "Theo dõi"
CIRCLE_FOLLOW_BUTTON_SELECTOR = (
    "button[data-follow-toggle='true'], button:has-text('Theo dõi')"
)

# Nút "＋ Tham gia"
CIRCLE_JOIN_BUTTON_SELECTOR = (
    "button[data-join-open='true'], button:has-text('Tham gia')"
)

# ==========================================
# 5. SELECTORS CHO TRANG CÁ NHÂN USER PROFILE (/app/u/...)
# ==========================================

# Nút "Theo dõi" trên trang cá nhân
USER_FOLLOW_BUTTON_SELECTOR = (
    "button[data-pp-follow='true'], button[data-pp-follow-state='follow'], "
    "button[data-pp-follow-state]:has-text('Theo dõi'), button[class*='_btn_'][data-pp-follow='true']"
)


