# Automation Tool - Temporary Email & OTP Verification (10minutemail.net)

Công cụ tự động hóa nhận email tạm từ **https://10minutemail.net/?lang=vi**, điều phối đồng thời 2 tab trình duyệt, refresh hòm thư đến lấy mã OTP xác minh tài khoản mục tiêu và quản lý thông qua giao diện đồ họa **CustomTkinter** trực quan.

---

## 🌟 Đặc điểm nổi bật

1. **Cơ chế Refresh chỉ áp dụng trên Tab Email (Tab 1)**:
   - Sử dụng `await email_page.reload(wait_until="domcontentloaded")` trên tab email tạm.
   - Tuyệt đối không reload `target_page` (Tab 2) và không reload toàn bộ `BrowserContext` để bảo toàn:
     - Dữ liệu form đang nhập
     - Phiên đăng nhập / session
     - Trạng thái gửi OTP
     - Bộ đếm ngược thời gian gửi lại (countdown OTP).
2. **Không hard-code selector**: Toàn bộ CSS Selectors được gom gọn trong file `selectors.py`.
3. **Tự động đổi email giữa các workflow**: Hàm `create_next_email(email_page)` tự động bấm nút `New Email` trên 10minutemail, đợi trang cấp địa chỉ mới trước khi sang workflow tiếp theo.
4. **Vượt xác minh bảo mật**: Xử lý mượt mà độ trễ và trang bảo mật của Cloudflare Turnstile trên 10minutemail.net.
5. **Giao diện CustomTkinter hiện đại**:
   - Theo dõi trạng thái trực tiếp: `RUNNING`, `PAUSED`, `STOPPED`, `IDLE`.
   - Bảng Checklist thời gian thực: `Register`, `Send OTP`, `Waiting Email`, `Refresh Inbox`, `OTP`, `Verify`, `Tasks`.
   - Cấu hình trực tiếp: Số workflow, Khoảng thời gian refresh (giây), Timeout OTP (giây), Chế độ Headless (ON/OFF), Target Website URL.
   - Hộp Log có gắn nhãn thời gian thực (`HH:MM:SS`).
   - Tích hợp sẵn **Mock Target Server** (`http://127.0.0.1:5000/register`) để kiểm thử ngay lập tức.

---

## 📂 Cấu trúc dự án

```text
d:\projectPython\tool-createUser\
│
├── selectors.py            # Chứa toàn bộ CSS selectors cho 10minutemail & Target Website
├── email_service.py        # Các hàm thao tác với 10minutemail (lấy mail, refresh, tìm OTP, tạo mail mới)
├── target_service.py       # Các hàm thao tác với Target website (điền mail, gửi OTP, nhập OTP, reset session)
├── mock_server.py          # Mock Target Server cục bộ phục vụ kiểm thử end-to-end
├── automation_worker.py    # Bộ điều phối quy trình Playwright đa luồng (Start, Pause, Resume, Stop)
├── gui.py                  # Giao diện đồ họa CustomTkinter
├── main.py                 # File chạy chính
└── requirements.txt        # Danh sách thư viện phụ thuộc
```

---

## 🚀 Hướng dẫn cài đặt & Khởi chạy

### 1. Cài đặt thư viện:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Khởi chạy Tool:
```bash
python main.py
```

### 3. Hướng dẫn sử dụng:
1. **Kiểm thử mẫu (Demo)**:
   - Mặc định checkbox `"Khởi chạy Mock Server cục bộ"` được bật với URL `http://127.0.0.1:5000/register`.
   - Nhấn nút **[ START AUTOMATION ]**.
   - Quan sát tab 1 mở 10minutemail.net, tab 2 mở Mock Target Form, thực hiện điền email, chờ refresh kiểm tra OTP và hoàn tất xác minh!
2. **Sử dụng với Website thực tế**:
   - Nhập URL trang web đăng ký vào ô `Target Website URL`.
   - Nếu cần tinh chỉnh selector theo form của website thực tế, chỉnh sửa trong [selectors.py](file:///d:/projectPython/tool-createUser/selectors.py).
   - Tùy chỉnh số lượng workflow, chu kỳ refresh (mặc định 3s) và timeout (mặc định 120s).
   - Nhấn **START**. Trong khi chạy, có thể nhấn **PAUSE** để tạm dừng hoặc **STOP** để hủy bất kỳ lúc nào.
