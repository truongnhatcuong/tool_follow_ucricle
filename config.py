"""
Module config.py
Quản lý cấu hình toàn diện cho Tool Automation:
- Danh sách URL Circles cần theo dõi và tham gia
- Thời gian nghỉ ngơi giữa các tài khoản (delay_between_workflows)
- Thời gian nghỉ giữa các Circle (delay_between_circles)
- Cấu hình số workflow, refresh interval, OTP timeout, Headless
Tự động lưu và đồng bộ với config.json để tiện update.
"""

import os
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger("Config")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key_ai": "sk-e2wq2BTpuFpT9tqKeiwvSYwMVKxwvwSLd6cZ9Tcrh9Ql5yx8",
    "ai_base_url": "https://api1.shupremium.com/v1",
    "ai_model": "gpt-4o-mini",
    "circle_urls": [
        "https://ucircle.net/app/c/7b944633-043c-445b-b516-aeeddb7bb7f9"
    ],
    "delay_between_workflows": 5,
    "delay_between_circles": 1,
    "total_workflows": 1000,
    "refresh_interval": 20,
    "otp_timeout": 120,
    "headless": False,
    "target_url": "https://ucircle.net/auth/login"
}


def load_config() -> Dict[str, Any]:
    """Tải cấu hình từ config.json, nếu chưa có thì tạo mới với giá trị mặc định"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = dict(DEFAULT_CONFIG)
                config.update(saved)
                return config
        except Exception as e:
            logger.warning(f"Lỗi khi đọc config.json: {e}. Sử dụng cấu hình mặc định.")
    
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]) -> None:
    """Lưu cấu hình ra file config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        logger.info(f"Đã lưu cấu hình vào {CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Lỗi khi lưu config.json: {e}")
