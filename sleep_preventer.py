"""
Module sleep_preventer.py
Cơ chế ngăn máy tính (macOS & Windows) tự động ngủ (Sleep / Standby)
trong suốt quá trình Tool Automation đang chạy tác vụ.
"""

import sys
import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("SleepPreventer")


class SleepPreventer:
    """
    Quản lý chế độ giữ máy tính luôn hoạt động (Stay Awake):
    - macOS: Dùng tiện ích hệ thống /usr/bin/caffeinate gắn với PID hiện tại.
    - Windows: Dùng hàm Win32 SetThreadExecutionState của kernel32.dll.
    - Tự động khôi phục chế độ ngủ bình thường khi tool hoàn tất hoặc dừng.
    """

    def __init__(self):
        self._caffeinate_proc: Optional[subprocess.Popen] = None
        self._is_active: bool = False

    def prevent_sleep(self, reason: str = "UCircle Automation Running") -> bool:
        """Kích hoạt cơ chế chống Sleep cho hệ điều hành"""
        if self._is_active:
            return True

        platform = sys.platform

        if platform == "darwin":
            # macOS: Chạy /usr/bin/caffeinate gắn theo PID của tiến trình Python hiện tại
            # -d: Ngăn màn hình ngủ
            # -i: Ngăn hệ thống ngủ khi rảnh rỗi (idle sleep)
            # -m: Ngăn ổ đĩa ngủ
            # -w <pid>: Tự động kết thúc khi tiến trình Python này đóng
            try:
                current_pid = str(os.getpid())
                caffeinate_path = "/usr/bin/caffeinate"
                if os.path.exists(caffeinate_path):
                    self._caffeinate_proc = subprocess.Popen(
                        [caffeinate_path, "-dim", "-w", current_pid],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self._is_active = True
                    logger.info("✓ [macOS] Đã kích hoạt caffeinate: Máy Mac sẽ không tự động ngủ khi tool đang chạy.")
                    return True
            except Exception as e:
                logger.warning(f"Không thể kích hoạt caffeinate trên macOS: {e}")

        elif platform.startswith("win"):
            # Windows: Gọi API SetThreadExecutionState của kernel32
            try:
                import ctypes
                ES_CONTINUOUS = 0x80000000
                ES_SYSTEM_REQUIRED = 0x00000001
                ES_AWAYMODE_REQUIRED = 0x00000040

                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
                )
                self._is_active = True
                logger.info("✓ [Windows] Đã kích hoạt SetThreadExecutionState: Máy tính sẽ không tự động ngủ.")
                return True
            except Exception as e:
                logger.warning(f"Không thể kích hoạt chống sleep trên Windows: {e}")

        else:
            logger.info("Nền tảng khác: Bỏ qua kích hoạt chống sleep.")

        return False

    def allow_sleep(self) -> None:
        """Khôi phục lại chế độ Sleep bình thường của hệ điều hành khi tool dừng"""
        if not self._is_active:
            return

        platform = sys.platform

        if platform == "darwin":
            if self._caffeinate_proc:
                try:
                    self._caffeinate_proc.terminate()
                    self._caffeinate_proc.wait(timeout=2)
                except Exception:
                    try:
                        self._caffeinate_proc.kill()
                    except Exception:
                        pass
                self._caffeinate_proc = None
            logger.info("✓ [macOS] Đã giải phóng caffeinate: Khôi phục chế độ ngủ bình thường của hệ thống.")

        elif platform.startswith("win"):
            try:
                import ctypes
                ES_CONTINUOUS = 0x80000000
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
                logger.info("✓ [Windows] Đã khôi phục chế độ ngủ bình thường của hệ thống.")
            except Exception:
                pass

        self._is_active = False


# Khởi tạo instance dùng chung
sleep_preventer = SleepPreventer()
