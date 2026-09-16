"""
Entry point cho Tool Tự động hóa đăng ký tài khoản & nhận OTP:
Chạy lệnh: python main.py
"""

import sys
import os

# Đảm bảo đường dẫn thư mục hiện tại nằm trong sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import run_gui

if __name__ == "__main__":
    run_gui()
