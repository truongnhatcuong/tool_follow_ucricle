"""
Module gui.py
Giao diện người dùng đồ họa (GUI) xây dựng bằng CustomTkinter:
- Khớp chính xác mockup ASCII: Status, Progress, Checklist trực tiếp, Điều khiển và Hộp Log cuộn
- Khung cấu hình chi tiết: Số workflows, Refresh interval, OTP timeout, Nghỉ giữa tài khoản, Nghỉ giữa Circle
- Form chuyên dụng Quản lý danh sách Circle URLs:
  + Hiển thị rõ ràng từng dòng URL
  + Đếm số lượng Circle (Badge)
  + Nút thêm nhanh Circle, Dán từ Clipboard, Xóa hết
  + Nút [ Lưu Danh Sách ] lưu trực tiếp vào config.json
"""

import sys
import os
import threading
import asyncio
import queue
from datetime import datetime
import customtkinter as ctk

from selectors import DEFAULT_TARGET_URL
from automation_worker import AutomationWorker
from mock_server import get_mock_server
from config import load_config, save_config
from sleep_preventer import sleep_preventer

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Automation Tool - UCircle Auto Creator & Circle Joiner")
        self.geometry("1100, 890")
        self.minsize(980, 800)

        # Worker & Threading state
        self.workers = []
        self.worker_threads = []
        self.msg_queue = queue.Queue()
        self.mock_server = get_mock_server()
        self.app_config = load_config()

        # Tạo giao diện
        self._create_ui()

        # Xử lý message queue an toàn trên UI thread
        self.after(100, self._process_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _create_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ========================================================
        # CỘT TRÁI: THEO DÕI TIẾN ĐỘ, CHECKLIST, NÚT BẤM & LOG
        # (Đúng theo mockup ASCII)
        # ========================================================
        left_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("#f1f5f9", "#1e293b"))
        left_frame.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(5, weight=1)  # Log chiếm phần mở rộng còn lại

        # 1. Tiêu đề
        title_label = ctk.CTkLabel(
            left_frame,
            text="Automation Tool",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("#0f172a", "#38bdf8")
        )
        title_label.grid(row=0, column=0, pady=(12, 4), sticky="ew")

        # 2. Status Badge
        status_card = ctk.CTkFrame(left_frame, corner_radius=8, fg_color=("#e2e8f0", "#0f172a"))
        status_card.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")

        self.status_label = ctk.CTkLabel(
            status_card,
            text="Status: ● IDLE",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#94a3b8"
        )
        self.status_label.pack(pady=6)

        # 3. Thông tin tiến độ & Checklist
        dash_card = ctk.CTkFrame(left_frame, corner_radius=8, fg_color=("#e2e8f0", "#0f172a"))
        dash_card.grid(row=2, column=0, padx=14, pady=4, sticky="ew")
        dash_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dash_card, text="Workflow:", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=12, pady=4, sticky="w"
        )
        self.lbl_workflow = ctk.CTkLabel(
            dash_card,
            text=f"0 / {self.app_config.get('total_workflows', 20)}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_workflow.grid(row=0, column=1, padx=12, pady=4, sticky="w")

        ctk.CTkLabel(dash_card, text="Current Email:", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=1, column=0, padx=12, pady=4, sticky="w"
        )
        self.lbl_email = ctk.CTkLabel(
            dash_card,
            text="(Chưa khởi tạo)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f59e0b"
        )
        self.lbl_email.grid(row=1, column=1, padx=12, pady=4, sticky="w")

        # Đường phân cách mỏng
        sep = ctk.CTkFrame(dash_card, height=1, fg_color=("#cbd5e1", "#334155"))
        sep.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=4)

        checklist_items = [
            ("Register:", "lbl_register", "-"),
            ("Send OTP:", "lbl_send_otp", "-"),
            ("Waiting Email:", "lbl_waiting_email", "-"),
            ("Refresh Inbox:", "lbl_refresh_count", "0 lần"),
            ("OTP:", "lbl_otp", "Waiting..."),
            ("Verify:", "lbl_verify", "-"),
            ("Tasks:", "lbl_tasks", "-"),
        ]

        self.check_labels = {}
        for row_idx, (title, attr_name, default_val) in enumerate(checklist_items, start=3):
            ctk.CTkLabel(
                dash_card,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#475569", "#cbd5e1")
            ).grid(row=row_idx, column=0, padx=12, pady=2, sticky="w")

            val_label = ctk.CTkLabel(
                dash_card,
                text=default_val,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#0284c7", "#38bdf8")
            )
            val_label.grid(row=row_idx, column=1, padx=12, pady=2, sticky="w")
            self.check_labels[attr_name] = val_label

        # 4. Nút bấm START / PAUSE / STOP
        btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=14, pady=(8, 4), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_start = ctk.CTkButton(
            btn_frame,
            text="START",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            command=self.on_start_clicked
        )
        self.btn_start.grid(row=0, column=0, padx=3, pady=2, sticky="ew")

        self.btn_pause = ctk.CTkButton(
            btn_frame,
            text="PAUSE",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#f59e0b",
            hover_color="#d97706",
            state="disabled",
            command=self.on_pause_clicked
        )
        self.btn_pause.grid(row=0, column=1, padx=3, pady=2, sticky="ew")

        self.btn_stop = ctk.CTkButton(
            btn_frame,
            text="STOP",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#ef4444",
            hover_color="#dc2626",
            state="disabled",
            command=self.on_stop_clicked
        )
        self.btn_stop.grid(row=0, column=2, padx=3, pady=2, sticky="ew")

        # Nút lớn START AUTOMATION
        self.btn_start_big = ctk.CTkButton(
            left_frame,
            text="[ START AUTOMATION ]",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=38,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.on_start_clicked
        )
        self.btn_start_big.grid(row=4, column=0, padx=14, pady=(2, 8), sticky="ew")

        # 5. Khung LOG trực tiếp
        log_frame = ctk.CTkFrame(left_frame, corner_radius=8, fg_color=("#e2e8f0", "#0f172a"))
        log_frame.grid(row=5, column=0, padx=14, pady=(0, 12), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header,
            text="LOG HOẠT ĐỘNG",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        ).grid(row=0, column=0, sticky="w")

        btn_clear_log = ctk.CTkButton(
            log_header,
            text="Xóa Log",
            width=65,
            height=22,
            font=ctk.CTkFont(size=11),
            fg_color="#475569",
            hover_color="#334155",
            command=self.clear_log
        )
        btn_clear_log.grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
            fg_color=("#ffffff", "#020617")
        )
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # ========================================================
        # CỘT PHẢI: CẤU HÌNH HỆ THỐNG & FORM QUẢN LÝ CIRCLES
        # ========================================================
        right_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("#f1f5f9", "#1e293b"))
        right_frame.grid(row=0, column=1, padx=12, pady=12, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)

        # ----------------------------------------------------
        # CARD 1: CẤU HÌNH TỰ ĐỘNG HÓA & AI KEY
        # ----------------------------------------------------
        config_card = ctk.CTkFrame(right_frame, corner_radius=8, fg_color=("#e2e8f0", "#0f172a"))
        config_card.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        config_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            config_card,
            text="CẤU HÌNH HỆ THỐNG & TÀI KHOẢN",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#38bdf8"
        ).grid(row=0, column=0, columnspan=3, padx=12, pady=(8, 4), sticky="w")

        # 0. Number of workers (Luồng)
        ctk.CTkLabel(config_card, text="Số luồng chạy song song:").grid(row=1, column=0, padx=12, pady=2, sticky="w")
        self.ent_workers = ctk.CTkEntry(config_card, width=70)
        self.ent_workers.insert(0, str(self.app_config.get("max_workers", 1)))
        self.ent_workers.grid(row=1, column=1, padx=6, pady=2, sticky="w")
        ctk.CTkLabel(config_card, text="luồng", text_color="#94a3b8").grid(row=1, column=2, padx=4, pady=2, sticky="w")

        # 1. Number of workflows
        ctk.CTkLabel(config_card, text="Số lượng workflows / luồng:").grid(row=2, column=0, padx=12, pady=2, sticky="w")
        self.ent_workflows = ctk.CTkEntry(config_card, width=70)
        self.ent_workflows.insert(0, str(self.app_config.get("total_workflows", 20)))
        self.ent_workflows.grid(row=2, column=1, padx=6, pady=2, sticky="w")

        # 2. Inbox refresh interval
        ctk.CTkLabel(config_card, text="Chu kỳ refresh email:").grid(row=3, column=0, padx=12, pady=2, sticky="w")
        self.ent_refresh_interval = ctk.CTkEntry(config_card, width=70)
        self.ent_refresh_interval.insert(0, str(self.app_config.get("refresh_interval", 15)))
        self.ent_refresh_interval.grid(row=3, column=1, padx=6, pady=2, sticky="w")
        ctk.CTkLabel(config_card, text="giây", text_color="#94a3b8").grid(row=3, column=2, padx=4, pady=2, sticky="w")

        # 3. OTP timeout
        ctk.CTkLabel(config_card, text="Thời gian chờ OTP tối đa:").grid(row=4, column=0, padx=12, pady=2, sticky="w")
        self.ent_otp_timeout = ctk.CTkEntry(config_card, width=70)
        self.ent_otp_timeout.insert(0, str(self.app_config.get("otp_timeout", 120)))
        self.ent_otp_timeout.grid(row=4, column=1, padx=6, pady=2, sticky="w")
        ctk.CTkLabel(config_card, text="giây", text_color="#94a3b8").grid(row=4, column=2, padx=4, pady=2, sticky="w")

        # 4. Delay between workflows (Nghỉ giữa các tài khoản)
        ctk.CTkLabel(config_card, text="Nghỉ ngơi giữa các tài khoản:").grid(row=5, column=0, padx=12, pady=2, sticky="w")
        self.ent_delay_workflows = ctk.CTkEntry(config_card, width=70)
        self.ent_delay_workflows.insert(0, str(self.app_config.get("delay_between_workflows", 5)))
        self.ent_delay_workflows.grid(row=5, column=1, padx=6, pady=2, sticky="w")
        ctk.CTkLabel(config_card, text="giây", text_color="#94a3b8").grid(row=5, column=2, padx=4, pady=2, sticky="w")

        # 5. Delay between circles
        ctk.CTkLabel(config_card, text="Nghỉ giữa mỗi Circle:").grid(row=6, column=0, padx=12, pady=2, sticky="w")
        self.ent_delay_circles = ctk.CTkEntry(config_card, width=70)
        self.ent_delay_circles.insert(0, str(self.app_config.get("delay_between_circles", 1)))
        self.ent_delay_circles.grid(row=6, column=1, padx=6, pady=2, sticky="w")
        ctk.CTkLabel(config_card, text="giây", text_color="#94a3b8").grid(row=6, column=2, padx=4, pady=2, sticky="w")

        # 6. Headless mode
        ctk.CTkLabel(config_card, text="Headless Mode:").grid(row=7, column=0, padx=12, pady=2, sticky="w")
        self.sw_headless = ctk.CTkSwitch(config_card, text="OFF (Mở trình duyệt trực tiếp)")
        if self.app_config.get("headless", False):
            self.sw_headless.select()
            self.sw_headless.configure(text="ON (Chạy ngầm ẩn)")
        self.sw_headless.grid(row=7, column=1, columnspan=2, padx=6, pady=2, sticky="w")
        self.sw_headless.configure(command=self._on_headless_toggle)

        # 7. Target URL
        ctk.CTkLabel(config_card, text="Target Website URL:").grid(row=8, column=0, padx=12, pady=2, sticky="w")
        self.ent_target_url = ctk.CTkEntry(config_card, width=320)
        self.ent_target_url.insert(0, self.app_config.get("target_url", DEFAULT_TARGET_URL))
        self.ent_target_url.grid(row=8, column=1, columnspan=2, padx=6, pady=2, sticky="ew")

        # 8. AI API Key
        ctk.CTkLabel(config_card, text="AI API Key:").grid(row=9, column=0, padx=12, pady=(2, 8), sticky="w")
        self.ent_api_key = ctk.CTkEntry(config_card, width=320, placeholder_text="Dán key AI vào đây...")
        if self.app_config.get("api_key_ai"):
            self.ent_api_key.insert(0, self.app_config.get("api_key_ai"))
        self.ent_api_key.grid(row=9, column=1, columnspan=2, padx=6, pady=(2, 8), sticky="ew")

        # ----------------------------------------------------
        # CARD 2: FORM CHUYÊN DỤNG QUẢN LÝ CIRCLE URLS
        # ----------------------------------------------------
        circle_card = ctk.CTkFrame(right_frame, corner_radius=8, fg_color=("#e2e8f0", "#0f172a"))
        circle_card.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        circle_card.grid_columnconfigure(0, weight=1)
        circle_card.grid_rowconfigure(2, weight=1)

        # Header card Circle
        circle_header = ctk.CTkFrame(circle_card, fg_color="transparent")
        circle_header.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="ew")
        circle_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            circle_header,
            text="DANH SÁCH CIRCLE URLS (THEO DÕI & THAM GIA)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        ).grid(row=0, column=0, sticky="w")

        self.lbl_circle_count = ctk.CTkLabel(
            circle_header,
            text=f"({len(self.app_config.get('circle_urls', []))} Circles)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10b981"
        )
        self.lbl_circle_count.grid(row=0, column=1, sticky="e")

        # Hàng thêm nhanh 1 Circle
        add_row = ctk.CTkFrame(circle_card, fg_color="transparent")
        add_row.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")
        add_row.grid_columnconfigure(0, weight=1)

        self.ent_quick_circle = ctk.CTkEntry(
            add_row,
            placeholder_text="Nhập hoặc dán link Circle (vd: https://ucircle.net/app/c/...) rồi nhấn Thêm"
        )
        self.ent_quick_circle.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        btn_add_circle = ctk.CTkButton(
            add_row,
            text="+ Thêm",
            width=70,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.on_add_quick_circle
        )
        btn_add_circle.grid(row=0, column=1, sticky="e")

        # Textbox hiển thị toàn bộ danh sách Circle URLs (to, rõ ràng)
        self.txt_circles = ctk.CTkTextbox(
            circle_card,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
            fg_color=("#ffffff", "#020617")
        )
        initial_circles = "\n".join(self.app_config.get("circle_urls", []))
        self.txt_circles.insert("1.0", initial_circles)
        self.txt_circles.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="nsew")

        # Hàng nút thao tác nhanh: Lưu danh sách, Dán, Xóa hết
        circle_actions = ctk.CTkFrame(circle_card, fg_color="transparent")
        circle_actions.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="ew")
        circle_actions.grid_columnconfigure((0, 1, 2), weight=1)

        btn_save_circles = ctk.CTkButton(
            circle_actions,
            text="💾 Lưu Danh Sách (config.json)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self.on_save_circles_clicked
        )
        btn_save_circles.grid(row=0, column=0, padx=3, pady=2, sticky="ew")

        btn_paste_circles = ctk.CTkButton(
            circle_actions,
            text="📋 Dán từ Clipboard",
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self.on_paste_clipboard_circles
        )
        btn_paste_circles.grid(row=0, column=1, padx=3, pady=2, sticky="ew")

        btn_clear_circles = ctk.CTkButton(
            circle_actions,
            text="🗑️ Xóa Hết",
            font=ctk.CTkFont(size=12),
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            command=self.on_clear_circles_clicked
        )
        btn_clear_circles.grid(row=0, column=2, padx=3, pady=2, sticky="ew")

    def _on_headless_toggle(self):
        is_on = self.sw_headless.get() == 1
        if is_on:
            self.sw_headless.configure(text="ON (Chạy ngầm ẩn)")
        else:
            self.sw_headless.configure(text="OFF (Mở trình duyệt trực tiếp)")

    def append_log(self, text: str):
        self.log_textbox.insert("end", text + "\n")
        self.log_textbox.see("end")

    def clear_log(self):
        self.log_textbox.delete("1.0", "end")

    def ui_callback(self, event_type: str, data: dict):
        self.msg_queue.put((event_type, data))

    def _get_current_circle_urls(self):
        raw_text = self.txt_circles.get("1.0", "end").strip()
        return [line.strip() for line in raw_text.splitlines() if line.strip()]

    def _update_circle_badge(self):
        urls = self._get_current_circle_urls()
        self.lbl_circle_count.configure(text=f"({len(urls)} Circles)")

    def on_add_quick_circle(self):
        """Thêm 1 Circle từ ô nhập nhanh vào Textbox"""
        new_url = self.ent_quick_circle.get().strip()
        if not new_url:
            return

        current_content = self.txt_circles.get("1.0", "end").strip()
        if current_content:
            self.txt_circles.insert("end", f"\n{new_url}")
        else:
            self.txt_circles.insert("1.0", new_url)

        self.ent_quick_circle.delete(0, "end")
        self._update_circle_badge()
        self.on_save_circles_clicked()

    def on_save_circles_clicked(self):
        """Lưu danh sách Circle và cấu hình vào config.json"""
        circle_urls = self._get_current_circle_urls()
        self.app_config["circle_urls"] = circle_urls
        self.app_config["api_key_ai"] = self.ent_api_key.get().strip()
        self.app_config["target_url"] = self.ent_target_url.get().strip() or DEFAULT_TARGET_URL
        try:
            self.app_config["max_workers"] = int(self.ent_workers.get().strip() or "1")
            self.app_config["delay_between_workflows"] = float(self.ent_delay_workflows.get().strip() or "5")
            self.app_config["delay_between_circles"] = float(self.ent_delay_circles.get().strip() or "1")
            self.app_config["total_workflows"] = int(self.ent_workflows.get().strip() or "20")
            self.app_config["refresh_interval"] = int(self.ent_refresh_interval.get().strip() or "15")
            self.app_config["otp_timeout"] = int(self.ent_otp_timeout.get().strip() or "120")
        except ValueError:
            pass

        save_config(self.app_config)
        self._update_circle_badge()
        self.append_log(f"✓ Đã lưu danh sách ({len(circle_urls)} Circles) vào config.json thành công!")

    def on_paste_clipboard_circles(self):
        """Dán nội dung từ clipboard vào Textbox"""
        try:
            clipboard_text = self.clipboard_get()
            if clipboard_text:
                self.txt_circles.insert("end", "\n" + clipboard_text.strip())
                self._update_circle_badge()
                self.on_save_circles_clicked()
        except Exception as e:
            self.append_log(f"Không thể đọc clipboard: {e}")

    def on_clear_circles_clicked(self):
        """Xóa hết danh sách Circle trong Textbox"""
        self.txt_circles.delete("1.0", "end")
        self._update_circle_badge()
        self.on_save_circles_clicked()

    def _process_queue(self):
        try:
            if not hasattr(self, "worker_states"):
                self.worker_states = {}
                self.worker_progress = {}

            while not self.msg_queue.empty():
                event_type, data = self.msg_queue.get_nowait()
                worker_id = data.get("worker_id", 1)

                if event_type == "log":
                    self.append_log(data.get("line", ""))

                elif event_type == "status":
                    status = data.get("status", "IDLE")
                    self.worker_states[worker_id] = status

                    # Tính toán global status
                    active_states = self.worker_states.values()
                    if "RUNNING" in active_states:
                        global_status = "RUNNING"
                    elif "PAUSED" in active_states:
                        global_status = "PAUSED"
                    elif "ERROR" in active_states:
                        global_status = "ERROR"
                    elif all(s == "COMPLETED" for s in active_states) and active_states:
                        global_status = "COMPLETED"
                    elif all(s in ["STOPPED", "IDLE", "COMPLETED"] for s in active_states) and active_states:
                        global_status = "STOPPED"
                    else:
                        global_status = "IDLE"

                    color_map = {
                        "RUNNING": ("#10b981", f"Status: ● RUNNING"),
                        "PAUSED": ("#f59e0b", f"Status: ● PAUSED"),
                        "STOPPED": ("#ef4444", f"Status: ● STOPPED"),
                        "COMPLETED": ("#06b6d4", f"Status: ● COMPLETED"),
                        "ERROR": ("#dc2626", f"Status: ● ERROR"),
                        "IDLE": ("#94a3b8", f"Status: ● IDLE"),
                    }
                    color, text = color_map.get(global_status, ("#94a3b8", f"Status: ● {global_status}"))
                    self.status_label.configure(text=text, text_color=color)

                    if global_status in ["STOPPED", "COMPLETED", "ERROR", "IDLE"]:
                        self.btn_start.configure(state="normal")
                        self.btn_start_big.configure(state="normal")
                        self.btn_pause.configure(state="disabled", text="PAUSE")
                        self.btn_stop.configure(state="disabled")
                    elif global_status == "RUNNING":
                        self.btn_start.configure(state="disabled")
                        self.btn_start_big.configure(state="disabled")
                        self.btn_pause.configure(state="normal", text="PAUSE")
                        self.btn_stop.configure(state="normal")
                    elif global_status == "PAUSED":
                        self.btn_pause.configure(state="normal", text="RESUME")

                elif event_type == "progress":
                    current = data.get("current", 0)
                    total = data.get("total", 0)
                    email = data.get("email", "")
                    
                    self.worker_progress[worker_id] = (current, total, email)
                    
                    total_current = sum(p[0] for p in self.worker_progress.values())
                    total_total = sum(p[1] for p in self.worker_progress.values())
                    self.lbl_workflow.configure(text=f"{total_current} / {total_total}")
                    
                    if email:
                        self.lbl_email.configure(text=f"[L{worker_id}] {email}")

                elif event_type == "checklist":
                    # Cập nhật checklist cho luồng cuối cùng thay đổi trạng thái
                    for key, val in data.items():
                        if key == "worker_id":
                            continue
                        lbl_key = f"lbl_{key}"
                        if lbl_key in self.check_labels:
                            display_val = str(val)
                            if key == "refresh_count":
                                display_val = f"{val} lần"
                            self.check_labels[lbl_key].configure(text=f"[L{worker_id}] {display_val}")

        except Exception as e:
            print(f"Error in UI queue processing: {e}")
        finally:
            self.after(80, self._process_queue)

    def on_start_clicked(self):
        try:
            max_workers = int(self.ent_workers.get().strip() or "1")
            workflows = int(self.ent_workflows.get().strip() or "20")
            refresh_interval = int(self.ent_refresh_interval.get().strip() or "15")
            otp_timeout = int(self.ent_otp_timeout.get().strip() or "120")
            delay_workflows = float(self.ent_delay_workflows.get().strip() or "5")
            delay_circles = float(self.ent_delay_circles.get().strip() or "1")
        except ValueError:
            self.append_log("Lỗi: Vui lòng nhập số hợp lệ cho các trường cấu hình!")
            return

        headless = (self.sw_headless.get() == 1)
        target_url = self.ent_target_url.get().strip() or DEFAULT_TARGET_URL
        api_key_ai = self.ent_api_key.get().strip()
        circle_urls = self._get_current_circle_urls()

        # Lưu cấu hình mới ra config.json
        new_cfg = {
            "api_key_ai": api_key_ai,
            "ai_base_url": self.app_config.get("ai_base_url", "https://api1.shupremium.com/v1"),
            "ai_model": self.app_config.get("ai_model", "gpt-4o-mini"),
            "circle_urls": circle_urls,
            "delay_between_workflows": delay_workflows,
            "delay_between_circles": delay_circles,
            "max_workers": max_workers,
            "total_workflows": workflows,
            "refresh_interval": refresh_interval,
            "otp_timeout": otp_timeout,
            "headless": headless,
            "target_url": target_url
        }
        save_config(new_cfg)
        self.app_config = new_cfg
        self._update_circle_badge()

        if "127.0.0.1:5000" in target_url:
            self.mock_server.start()

        self.workers = []
        self.worker_threads = []

        self.append_log(f"Bắt đầu khởi chạy {max_workers} luồng tự động hóa...")

        for i in range(max_workers):
            worker_id = i + 1
            worker = AutomationWorker(
                worker_id=worker_id,
                total_workflows=workflows,
                refresh_interval=refresh_interval,
                otp_timeout=otp_timeout,
                headless=headless,
                target_url=target_url,
                circle_urls=circle_urls,
                delay_between_workflows=delay_workflows,
                delay_between_circles=delay_circles,
                api_key_ai=api_key_ai,
                ai_base_url=new_cfg.get("ai_base_url", "https://api1.shupremium.com/v1"),
                ai_model=new_cfg.get("ai_model", "gpt-4o-mini"),
                ui_callback=self.ui_callback
            )
            self.workers.append(worker)

            def run_worker_thread(w=worker, start_delay=(worker_id - 1) * 4):
                async def delayed_run():
                    if start_delay > 0:
                        w.log(f"Đang chờ {start_delay}s để tránh quá tải khi khởi động luồng...")
                        await asyncio.sleep(start_delay)
                    await w.run()
                asyncio.run(delayed_run())

            t = threading.Thread(target=run_worker_thread, daemon=True)
            self.worker_threads.append(t)
            t.start()

    def on_pause_clicked(self):
        if not self.workers:
            return
        
        # Lấy trạng thái từ worker đầu tiên làm chuẩn
        is_paused = self.workers[0].is_paused
        for worker in self.workers:
            if is_paused:
                worker.resume()
            else:
                worker.pause()

    def on_stop_clicked(self):
        for worker in self.workers:
            worker.stop()
        sleep_preventer.allow_sleep()

    def on_closing(self):
        """Dọn dẹp tài nguyên và khôi phục chế độ sleep khi đóng cửa sổ ứng dụng"""
        try:
            for worker in self.workers:
                worker.stop()
            sleep_preventer.allow_sleep()
        except Exception:
            pass
        self.destroy()


def run_gui():
    app = AutomationApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
