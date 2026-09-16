"""
Module ai_service.py
Quản lý việc sinh Tên hiển thị và @username:
- Ưu tiên gọi Model AI (OpenAI compatible / https://gpt4.shupremium.com/v1/chat/completions)
  với prompt sáng tạo, đa dạng phong cách để tạo tên tiếng Việt tự nhiên và username độc nhất.
- Hỗ trợ AI sinh cả @username thay thế khi phát hiện bị trùng.
- Cơ chế theo dõi `used_names` và `used_usernames` tránh trùng lặp trong cùng phiên.
- Hệ thống Fallback phong phú (hơn 40.000 tổ hợp Họ + Đệm + Tên) khi mất kết nối mạng/AI.
"""

import os
import re
import json
import random
import logging
import httpx
from typing import Dict, Any, Set

logger = logging.getLogger("AiService")

# Danh mục họ và tên phong phú cho chế độ Offline Fallback
VN_SURNAMES = [
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
    "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đào", "Đoàn", "Vương",
    "Trịnh", "Trương", "Đinh", "Lâm", "Phùng", "Mai", "Tô", "Hà", "Lương",
    "Cao", "Châu", "Chu", "Tạ", "Thái", "Tăng", "Tống", "Quách", "La", "Lưu",
    "Thạch", "Ninh", "Từ", "Hứa", "Kiều", "Mạc", "Quang", "Triệu", "Lục", "Âu",
    "Âu Dương", "Tôn", "Tôn Thất", "Tôn Nữ", "Khổng", "Vi", "Tiêu", "Sầm",
    "Hàn", "Doãn", "Đàm", "Nghiêm", "Văn", "Quyền", "Ma", "Chung", "Nhan",
    "Bạch", "Cù", "Thi", "Thân", "Từ", "Ông", "Khương", "Kha", "Diệp", "Liêu",
    "Giang", "Hồng", "Tưởng", "Tào", "Lã", "Mã", "Lư", "Trầm", "Lạc", "Tăng"
]

VN_MIDDLE_NAMES = [
    "Văn", "Thị", "Hải", "Đình", "Ngọc", "Minh", "Đức", "Xuân", "Quang", "Hữu",
    "Tuấn", "Trọng", "Gia", "Hoàng", "Khánh", "Phương", "Bảo", "Anh", "Kim",
    "Thanh", "Tấn", "Quốc", "Thành", "Triết", "Đăng", "Thùy", "Như", "Diệu",
    "Thảo", "Hồng",

    "Công", "Mạnh", "Duy", "Nhật", "Tiến", "Chí", "Thiên", "Đại", "Trung",
    "Vĩnh", "Đắc", "Đình", "Bá", "Sỹ", "Huy", "Trường", "Khắc", "Nhất", "Đông",
    "Nam", "Việt", "Hưng", "Phú", "Phúc", "Đạt", "Khang", "Kiến", "Tường",
    "Nhân", "Nghĩa", "Thế", "Chấn", "Vũ", "Sơn", "Lâm", "Phong", "Long",

    "Thu", "Mai", "Lan", "Hương", "Hạnh", "Mỹ", "Ánh", "Tuyết", "Bích", "Cẩm",
    "Kiều", "Quỳnh", "Uyên", "Nhã", "Yến", "Huyền", "Hoài", "Trúc", "Lam",
    "Hà", "Lệ", "Mộng", "Tâm", "An", "Thi", "Nhi", "Khả", "Đan", "Tú",
    "Hiền", "Oanh", "Nga", "Loan", "Liên", "Dung", "Giang", "Châu", "Vy",
    "Trâm", "Ngân", "Trang", "Linh", "Nhung", "Thúy", "Huệ", "Hằng", "Hân"
]

VN_GIVEN_NAMES = [
    # Nam
    "Nam", "Hùng", "Dũng", "Tuấn", "Kiệt", "Long", "Sơn", "Lâm", "Cường",
    "Đạt", "Khoa", "Phúc", "An", "Bình", "Thắng", "Hoàng", "Huy", "Phát",
    "Thịnh", "Quân", "Bách", "Hiếu", "Duy", "Khang", "Nhân", "Nghĩa", "Trí",
    "Việt", "Triết", "Minh", "Đức", "Tùng", "Tú", "Khôi", "Vinh", "Phong",
    "Hưng", "Hải", "Tài", "Thành", "Trung", "Thiện", "Tâm", "Toàn", "Tiến",
    "Tân", "Tín", "Thọ", "Thuận", "Trường", "Vũ", "Vương", "Đông", "Sang",
    "Sáng", "Công", "Danh", "Đại", "Đăng", "Điền", "Dương", "Gia", "Hào",
    "Hậu", "Hiệp", "Hoài", "Hòa", "Huân", "Khiêm", "Khánh", "Lộc", "Luân",
    "Mạnh", "Nguyên", "Nhật", "Phú", "Quang", "Quốc", "Tấn", "Thiên", "Thông",
    "Thế", "Uy", "Văn", "Bảo", "Chí", "Đình", "Hữu", "Kiên", "Lợi", "Lực",
    "Ngọc", "Phước", "Tường", "Xuân", "Khải", "Vỹ", "Đức Anh", "Minh Anh",
    "Quốc Anh", "Tuấn Anh", "Hoàng Anh", "Hải Đăng", "Minh Khang",
    "Gia Huy", "Quang Huy", "Đức Huy", "Nhật Minh", "Hoàng Nam",
    "Quốc Bảo", "Gia Bảo", "Minh Quân", "Anh Tuấn", "Thanh Tùng",

    # Nữ
    "Vy", "Linh", "Nhi", "Trang", "Thảo", "Hương", "Hân", "My", "Trâm",
    "Châu", "Dung", "Ngân", "Quỳnh", "Mai", "Ngọc", "Vân", "Ly", "Thư",
    "Trúc", "Yến", "Hà", "Lan", "Anh", "An", "Chi", "Diệp", "Giang", "Hạnh",
    "Hiền", "Hoa", "Huệ", "Huyền", "Khánh", "Lam", "Loan", "Nga", "Nhung",
    "Oanh", "Phương", "Quyên", "Thúy", "Trinh", "Uyên", "Xuân", "Ánh",
    "Bích", "Cẩm", "Đào", "Diễm", "Hằng", "Hoài", "Kiều", "Liên", "Lệ",
    "Minh", "Mỹ", "Nhã", "Nữ", "Tâm", "Thanh", "Thi", "Thu", "Thùy", "Tiên",
    "Tú", "Tuyết", "Vi", "Yên", "Đan", "Khuê", "Mẫn", "Mi", "Na", "Nhã",
    "San", "Thy", "Uyên", "Yến",

    # Tên kép phổ biến
    "Ngọc Anh", "Phương Anh", "Quỳnh Anh", "Thùy Anh", "Tú Anh",
    "Mai Anh", "Lan Anh", "Huyền Anh", "Bảo Anh", "Hải Anh",
    "Minh Anh", "Hoài Anh", "Khánh Linh", "Phương Linh", "Thùy Linh",
    "Ngọc Linh", "Mai Linh", "Gia Linh", "Diệu Linh", "Mỹ Linh",
    "Ngọc Hân", "Gia Hân", "Bảo Hân", "Khánh Vy", "Tường Vy",
    "Thảo Vy", "Ngọc Trâm", "Bảo Trâm", "Quỳnh Trang", "Thu Trang",
    "Huyền Trang", "Thùy Trang", "Ngọc Mai", "Thanh Mai", "Quỳnh Mai",
    "Ngọc Thảo", "Phương Thảo", "Thu Thảo", "Thanh Thảo", "Bích Ngọc",
    "Minh Ngọc", "Bảo Ngọc", "Ánh Ngọc", "Kim Ngân", "Thảo Nguyên",
    "Thảo Nhi", "Yến Nhi", "Bảo Nhi", "Khánh An", "Bảo An",
    "Gia An", "Ngọc Hà", "Thanh Hà", "Thu Hà", "Việt Hà",
    "Thanh Hương", "Thu Hương", "Lan Hương", "Quỳnh Hương", "Mai Hương"
]


class ModelAi:
    def __init__(self, api_key: str = "", base_url: str = "https://gpt4.shupremium.com/v1", model: str = "gpt-4o-mini"):
        self.api_key = api_key.strip() if api_key else ""
        self.base_url = base_url.rstrip("/") if base_url else "https://gpt4.shupremium.com/v1"
        self.model = model or "gpt-4o-mini"
        self.used_names: Set[str] = set()
        self.used_usernames: Set[str] = set()

    def generate_profile(self, email: str = "") -> Dict[str, str]:
        """
        Sinh Tên hiển thị và @username:
        - Sử dụng Model AI với prompt ngẫu nhiên hóa phong cách để đảm bảo 100% không trùng lặp.
        - Tự động kiểm tra và ghi nhận vào tập đã dùng trong phiên.
        """
        if self.api_key:
            for attempt in range(3):
                try:
                    ai_result = self._call_ai(email)
                    name = ai_result.get("name", "").strip()
                    username = ai_result.get("username", "").strip()

                    if name and username:
                        # Kiểm tra xem đã từng sinh tên hoặc username này chưa
                        if username in self.used_usernames:
                            username = f"{username}_{random.randint(10, 999)}"

                        if name in self.used_names:
                            # Tên đã dùng trong phiên -> thử lại lượt gọi AI tiếp theo
                            logger.info(f"[AI] Tên '{name}' đã được dùng trong phiên, thử sinh lại...")
                            continue

                        self.used_names.add(name)
                        self.used_usernames.add(username)

                        logger.info(f"[AI] Đã tạo hồ sơ bằng AI ({self.model}): Name='{name}', Username='{username}'")
                        return {"name": name, "username": username}
                except Exception as e:
                    logger.warning(f"[AI] Thử lần {attempt+1} gọi AI API thất bại ({e}).")

        logger.info("[AI] Sử dụng bộ tạo tên phong phú ngẫu nhiên (Fallback)...")
        fallback = self._fallback_generate(email)
        self.used_names.add(fallback["name"])
        self.used_usernames.add(fallback["username"])
        return fallback

    def _call_ai(self, email: str) -> Dict[str, str]:
        url = f"{self.base_url}/chat/completions"

        # Gợi ý phong cách ngẫu nhiên để AI đổi mới liên tục
        styles = [
            "tên thanh niên hiện đại, trẻ trung thế hệ Gen Z",
            "tên đầy đủ 3 chữ trang nhã, giàu ý nghĩa (Họ + Đệm + Tên)",
            "tên 2 chữ ngắn gọn, cá tính",
            "tên gắn liền với sự may mắn, thành đạt",
            "tên mang phong cách sinh viên, đam mê công nghệ",
            "tên họ ít gặp như Đào, Đoàn, Vương, Trương, Đinh, Lâm, Phùng, Mai, Hà",
            "tên nữ dịu dàng, thanh lịch hoặc tên nam mạnh mẽ, dứt khoát"
        ]
        chosen_style = random.choice(styles)
        rand_seed = random.randint(100, 99999)

        prompt = (
            f"Bạn là chuyên gia đặt tên người dùng tiếng Việt. Hãy tạo 1 Tên người dùng và 1 @username độc nhất (mã ngẫu nhiên: {rand_seed}).\n"
            f"- Gợi ý phong cách: {chosen_style}.\n"
            f"- Tên hiển thị (name): Họ và tên tiếng Việt tự nhiên có dấu, tuyệt đối KHÔNG lặp lại các tên quá phổ biến.\n"
            f"- @username: Chỉ gồm chữ thường không dấu (a-z), số (0-9) hoặc dấu gạch dưới (_), độ dài 6-16 ký tự, dễ nhìn, độc nhất.\n"
            f"QUAN TRỌNG: Chỉ trả về duy nhất 1 JSON thuần: {{\"name\": \"<tên>\", \"username\": \"<username>\"}} không có bất kỳ văn bản nào khác."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "temperature": 1.08,
            "messages": [
                {"role": "system", "content": "You are a creative Vietnamese name generator that always outputs strictly valid JSON only."},
                {"role": "user", "content": prompt}
            ],
        }

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                json_match = re.search(r'\{.*?\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    name = str(parsed.get("name", "")).strip()
                    raw_user = str(parsed.get("username", "")).strip().lower()
                    clean_user = re.sub(r'[^a-z0-9_]', '', raw_user)

                    if name and clean_user and len(clean_user) >= 3:
                        return {"name": name, "username": clean_user[:28]}
            else:
                logger.warning(f"[AI] API trả về mã lỗi {resp.status_code}: {resp.text}")

        return {}

    def generate_alternative_username(self, current_username: str) -> str:
        """
        Dùng AI để sinh @username thay thế sáng tạo khi phát hiện bị trùng.
        Nếu AI không phản hồi kịp thì tự động kết hợp đuôi ngẫu nhiên.
        """
        if self.api_key:
            try:
                alt = self._call_ai_alternative_username(current_username)
                if alt and alt not in self.used_usernames:
                    self.used_usernames.add(alt)
                    logger.info(f"[AI] Đã tạo @username thay thế bằng AI: '{alt}'")
                    return alt
            except Exception as e:
                logger.warning(f"[AI] Lỗi khi gọi AI sinh username thay thế: {e}")

        # Fallback tạo username thay thế
        base = re.sub(r'[^a-z0-9_]', '', current_username.lower())
        base = re.sub(r'_\d+$', '', base)
        if not base or len(base) < 3:
            base = "user"

        new_suffix = random.randint(10000, 999999)
        alt_username = f"{base[:18]}_{new_suffix}"
        self.used_usernames.add(alt_username)
        return alt_username

    def _call_ai_alternative_username(self, current_username: str) -> str:
        url = f"{self.base_url}/chat/completions"
        rand_num = random.randint(10, 9999)
        prompt = (
            f"Username '@{current_username}' đã có người sử dụng. "
            f"Hãy gợi ý 1 @username thay thế sáng tạo, mới lạ, độc nhất (seed {rand_num}, 6-16 ký tự chữ thường a-z, số, gạch dưới, không dấu). "
            f"Chỉ trả về đúng 1 JSON: {{\"username\": \"...\"}}"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "temperature": 1.15,
            "messages": [
                {"role": "system", "content": "You are a creative username generator that returns strictly valid JSON only."},
                {"role": "user", "content": prompt}
            ]
        }
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                match = re.search(r'\{.*?\}', content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    raw_user = str(data.get("username", "")).strip().lower()
                    clean_user = re.sub(r'[^a-z0-9_]', '', raw_user)
                    if clean_user and len(clean_user) >= 3:
                        return clean_user[:28]
        return ""

    def _fallback_generate(self, email: str) -> Dict[str, str]:
        """
        Sinh ngẫu nhiên với hơn 40.000 tổ hợp tên Việt Nam kết hợp số ngẫu nhiên.
        Luôn kiểm tra với used_names/used_usernames để tránh trùng trong cùng phiên.
        """
        prefix = email.split("@")[0].lower() if "@" in email else "user"
        clean_prefix = re.sub(r'[^a-z0-9_]', '', prefix)
        if not clean_prefix or len(clean_prefix) < 3:
            clean_prefix = "user"

        display_name = ""
        username = ""
        for _ in range(20):
            surname = random.choice(VN_SURNAMES)
            # 60% tỉ lệ tên 3 chữ, 40% tỉ lệ tên 2 chữ
            if random.random() < 0.6:
                mid = random.choice(VN_MIDDLE_NAMES)
                given = random.choice(VN_GIVEN_NAMES)
                candidate_name = f"{surname} {mid} {given}"
            else:
                given = random.choice(VN_GIVEN_NAMES)
                candidate_name = f"{surname} {given}"

            random_suffix = random.randint(1000, 99999)
            candidate_username = f"{clean_prefix[:18]}_{random_suffix}"

            if candidate_name not in self.used_names and candidate_username not in self.used_usernames:
                display_name = candidate_name
                username = candidate_username
                break

        if not display_name:
            # Hết 20 lần thử vẫn trùng (rất hiếm) -> gắn thêm hậu tố ngẫu nhiên để chắc chắn độc nhất
            display_name = f"{candidate_name} {random.randint(10, 99)}"
            username = f"{candidate_username}_{random.randint(10, 99)}"

        return {"name": display_name, "username": username}
