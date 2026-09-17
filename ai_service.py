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
    # Họ phổ biến
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
    "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đào", "Đoàn", "Vương",
    "Trịnh", "Trương", "Đinh", "Lâm", "Phùng", "Mai", "Tô", "Hà", "Lương",

    # Họ ít phổ biến hơn
    "Cao", "Châu", "Chu", "Tạ", "Thái", "Tăng", "Tống", "Quách", "La", "Lưu",
    "Thạch", "Ninh", "Từ", "Hứa", "Kiều", "Mạc", "Quang", "Triệu", "Lục", "Âu",
    "Tôn", "Khổng", "Vi", "Tiêu", "Sầm", "Hàn", "Doãn", "Đàm", "Nghiêm",
    "Văn", "Quyền", "Ma", "Chung", "Nhan", "Bạch", "Cù", "Thi", "Thân",
    "Ông", "Khương", "Kha", "Diệp", "Liêu", "Giang", "Hồng", "Tưởng",
    "Tào", "Lã", "Mã", "Lư", "Trầm", "Lạc",

    # Họ khác
    "An", "Bàn", "Bế", "Biện", "Bồ", "Cam", "Cầm", "Chế", "Cổ", "Danh",
    "Dư", "Đậu", "Điêu", "Điền", "Giáp", "Hán", "Hầu", "Kim", "Khuất",
    "Mạnh", "Nông", "Phí", "Sái", "Tiền", "Tiết", "Trang", "Ung", "Ứng",
    "Vạn", "Vệ", "Xà", "Nhâm", "Nhữ", "Phó", "Quản", "Sử", "Thẩm",
    "Thường", "Kỷ", "Lôi", "Nhạc", "Nhiếp", "Khâu", "Đường", "Hình",

    # Một số họ dân tộc / vùng miền
    "Giàng", "Vàng", "Sùng", "Thào", "Mùa", "Lù", "Lầu", "Seo", "Vừ",
    "Chảo", "Tẩn", "Lìn", "Lẻo", "Chíu", "Phàn", "Quàng", "Lò", "Pờ",

    # Họ kép / dòng họ
    "Âu Dương",
    "Tôn Thất",
    "Tôn Nữ",
]


VN_MIDDLE_NAMES = [
    # Tên đệm rất phổ biến
    "Văn", "Thị", "Hải", "Đình", "Ngọc", "Minh", "Đức", "Xuân", "Quang",
    "Hữu", "Tuấn", "Trọng", "Gia", "Hoàng", "Khánh", "Phương", "Bảo",
    "Anh", "Kim", "Thanh", "Tấn", "Quốc", "Thành", "Triết", "Đăng",
    "Thùy", "Như", "Diệu", "Thảo", "Hồng",

    # Nam
    "Công", "Mạnh", "Duy", "Nhật", "Tiến", "Chí", "Thiên", "Đại", "Trung",
    "Vĩnh", "Đắc", "Bá", "Sỹ", "Huy", "Trường", "Khắc", "Nhất", "Đông",
    "Nam", "Việt", "Hưng", "Phú", "Phúc", "Đạt", "Khang", "Kiến", "Tường",
    "Nhân", "Nghĩa", "Thế", "Chấn", "Vũ", "Sơn", "Lâm", "Phong", "Long",
    "Khải", "Kiệt", "Khoa", "Quân", "Bách", "Hiếu", "Trí", "Tùng", "Khôi",
    "Vinh", "Tài", "Thiện", "Toàn", "Tân", "Tín", "Thuận", "Danh", "Hào",
    "Hậu", "Hiệp", "Huân", "Khiêm", "Lộc", "Luân", "Nguyên", "Thông",
    "Uy", "Kiên", "Lợi", "Lực", "Phước", "Cảnh", "Chính", "Dũng", "Hùng",
    "Sáng", "Sang", "Thắng", "Thịnh", "Phát",

    # Nữ
    "Thu", "Mai", "Lan", "Hương", "Hạnh", "Mỹ", "Ánh", "Tuyết", "Bích",
    "Cẩm", "Kiều", "Quỳnh", "Uyên", "Nhã", "Yến", "Huyền", "Hoài", "Trúc",
    "Lam", "Hà", "Lệ", "Mộng", "Tâm", "An", "Thi", "Nhi", "Khả", "Đan",
    "Tú", "Hiền", "Oanh", "Nga", "Loan", "Liên", "Dung", "Giang", "Châu",
    "Vy", "Trâm", "Ngân", "Trang", "Linh", "Nhung", "Thúy", "Huệ", "Hằng",
    "Hân", "Chi", "Diệp", "Hoa", "Quyên", "Trinh", "Tiên", "Thư", "Vân",
    "Ly", "Yên", "Khuê", "Mẫn", "Mi", "Thy", "San", "Na",

    # Tên đệm bổ sung
    "Ân", "Bình", "Chu", "Đoan", "Hạo", "Hiển", "Hiếu", "Hoàng",
    "Hồng", "Hợp", "Huỳnh", "Kỳ", "Mỹ", "Nghi", "Nghiêm", "Phong",
    "Quý", "Tịnh", "Trí", "Trực", "Uyên", "Vi", "Vĩ", "Yên",

    # Đệm hai âm tiết nam
    "Anh Đức",
    "Anh Dũng",
    "Anh Khoa",
    "Anh Minh",
    "Anh Quân",
    "Anh Tuấn",
    "Bảo Châu",
    "Bảo Long",
    "Bảo Minh",
    "Bảo Nam",
    "Bảo Quốc",
    "Công Danh",
    "Công Minh",
    "Công Thành",
    "Đình Anh",
    "Đình Duy",
    "Đình Huy",
    "Đình Khang",
    "Đình Khôi",
    "Đình Nam",
    "Đình Phong",
    "Đình Quân",
    "Đình Trung",
    "Đức Anh",
    "Đức Duy",
    "Đức Huy",
    "Đức Khang",
    "Đức Long",
    "Đức Minh",
    "Đức Phúc",
    "Đức Thịnh",
    "Đức Trung",
    "Gia Bảo",
    "Gia Huy",
    "Gia Khánh",
    "Gia Khiêm",
    "Gia Khang",
    "Gia Minh",
    "Gia Phúc",
    "Gia Thành",
    "Hải Anh",
    "Hải Đăng",
    "Hải Dương",
    "Hải Minh",
    "Hoàng Anh",
    "Hoàng Duy",
    "Hoàng Hải",
    "Hoàng Long",
    "Hoàng Minh",
    "Hoàng Nam",
    "Hoàng Phúc",
    "Hữu Đạt",
    "Hữu Đức",
    "Hữu Khang",
    "Hữu Minh",
    "Hữu Phúc",
    "Hữu Thành",
    "Khánh Duy",
    "Khánh Hưng",
    "Khánh Minh",
    "Minh Anh",
    "Minh Đức",
    "Minh Duy",
    "Minh Hiếu",
    "Minh Hoàng",
    "Minh Huy",
    "Minh Khang",
    "Minh Khôi",
    "Minh Long",
    "Minh Nhật",
    "Minh Phúc",
    "Minh Quân",
    "Minh Trí",
    "Nhật Anh",
    "Nhật Duy",
    "Nhật Huy",
    "Nhật Minh",
    "Quang Anh",
    "Quang Huy",
    "Quang Minh",
    "Quang Vinh",
    "Quốc Anh",
    "Quốc Bảo",
    "Quốc Huy",
    "Quốc Khánh",
    "Quốc Minh",
    "Quốc Việt",
    "Thanh Bình",
    "Thanh Duy",
    "Thanh Hải",
    "Thanh Tùng",
    "Thiên Ân",
    "Thiên Bảo",
    "Thiên Minh",
    "Thiên Phúc",
    "Trọng Đức",
    "Trọng Nghĩa",
    "Trọng Nhân",
    "Trọng Tấn",
    "Tuấn Anh",
    "Tuấn Kiệt",
    "Tuấn Minh",

    # Đệm hai âm tiết nữ
    "Ánh Dương",
    "Ánh Ngọc",
    "Bảo Anh",
    "Bảo Châu",
    "Bảo Hân",
    "Bảo Ngọc",
    "Bích Ngọc",
    "Cẩm Tú",
    "Diệu Anh",
    "Diệu Linh",
    "Diệu My",
    "Diệu Ngọc",
    "Gia Hân",
    "Gia Linh",
    "Hải Anh",
    "Hoài An",
    "Hoài Anh",
    "Hoài Thương",
    "Hồng Anh",
    "Hồng Hạnh",
    "Hồng Nhung",
    "Huyền Anh",
    "Huyền My",
    "Huyền Trang",
    "Khánh An",
    "Khánh Chi",
    "Khánh Linh",
    "Khánh Ly",
    "Khánh Ngân",
    "Khánh Vy",
    "Kim Anh",
    "Kim Chi",
    "Kim Ngân",
    "Lan Anh",
    "Lan Chi",
    "Lan Hương",
    "Mai Anh",
    "Mai Hương",
    "Mai Linh",
    "Minh Anh",
    "Minh Châu",
    "Minh Hà",
    "Minh Ngọc",
    "Mỹ Anh",
    "Mỹ Duyên",
    "Mỹ Hạnh",
    "Mỹ Linh",
    "Mỹ Ngọc",
    "Ngọc Anh",
    "Ngọc Ánh",
    "Ngọc Bích",
    "Ngọc Diệp",
    "Ngọc Hà",
    "Ngọc Hân",
    "Ngọc Lan",
    "Ngọc Linh",
    "Ngọc Mai",
    "Ngọc Trâm",
    "Ngọc Trang",
    "Phương Anh",
    "Phương Linh",
    "Phương Mai",
    "Phương Nhi",
    "Phương Thảo",
    "Quỳnh Anh",
    "Quỳnh Hương",
    "Quỳnh Mai",
    "Quỳnh Như",
    "Quỳnh Trang",
    "Thanh Hà",
    "Thanh Hương",
    "Thanh Mai",
    "Thanh Thảo",
    "Thảo Linh",
    "Thảo My",
    "Thảo Nhi",
    "Thảo Nguyên",
    "Thảo Vy",
    "Thu Hà",
    "Thu Hương",
    "Thu Thảo",
    "Thu Trang",
    "Thùy Anh",
    "Thùy Dương",
    "Thùy Linh",
    "Thùy Trang",
    "Trúc Anh",
    "Trúc Linh",
    "Tường Vy",
    "Tú Anh",
    "Uyên Nhi",
    "Yến Nhi",
]


VN_GIVEN_NAMES = [
    # ========================================================
    # NAM - TÊN ĐƠN
    # ========================================================

    "An", "Ân", "Anh", "Bách", "Bảo", "Bình", "Cảnh", "Chí", "Chính",
    "Công", "Cường", "Danh", "Đại", "Đăng", "Đạt", "Điền", "Đình", "Đông",
    "Đức", "Dũng", "Duy", "Dương", "Gia", "Hào", "Hải", "Hậu", "Hiển",
    "Hiệp", "Hiếu", "Hoài", "Hoàng", "Hòa", "Huân", "Hùng", "Hưng", "Hữu",
    "Huy", "Khang", "Khải", "Khánh", "Khiêm", "Khoa", "Khôi", "Kiên",
    "Kiệt", "Lâm", "Lộc", "Lợi", "Long", "Luân", "Lực", "Mạnh", "Minh",
    "Nam", "Nghĩa", "Nguyên", "Nhân", "Nhật", "Phong", "Phát", "Phú",
    "Phúc", "Phước", "Quân", "Quang", "Quốc", "Sang", "Sáng", "Sơn",
    "Tài", "Tâm", "Tân", "Tấn", "Thái", "Thành", "Thắng", "Thiện",
    "Thiên", "Thịnh", "Thông", "Thuận", "Thế", "Thọ", "Tiến", "Tín",
    "Toàn", "Trí", "Triết", "Trọng", "Trung", "Trường", "Tùng", "Tú",
    "Tuấn", "Tường", "Uy", "Văn", "Việt", "Vinh", "Vũ", "Vương", "Xuân",

    # ========================================================
    # NAM - TÊN KÉP
    # ========================================================

    "Anh Dũng",
    "Anh Đức",
    "Anh Hào",
    "Anh Khoa",
    "Anh Khôi",
    "Anh Kiệt",
    "Anh Minh",
    "Anh Quân",
    "Anh Sơn",
    "Anh Tài",
    "Anh Tuấn",

    "Bảo An",
    "Bảo Anh",
    "Bảo Duy",
    "Bảo Hưng",
    "Bảo Khang",
    "Bảo Khánh",
    "Bảo Lâm",
    "Bảo Long",
    "Bảo Minh",
    "Bảo Nam",
    "Bảo Nguyên",
    "Bảo Phúc",
    "Bảo Quân",
    "Bảo Quốc",
    "Bảo Sơn",
    "Bảo Trung",

    "Công Danh",
    "Công Hậu",
    "Công Minh",
    "Công Thành",
    "Công Thiện",
    "Công Vinh",

    "Đình Anh",
    "Đình Duy",
    "Đình Đức",
    "Đình Hải",
    "Đình Hiếu",
    "Đình Huy",
    "Đình Khang",
    "Đình Khôi",
    "Đình Long",
    "Đình Nam",
    "Đình Phong",
    "Đình Phúc",
    "Đình Quân",
    "Đình Sơn",
    "Đình Trung",
    "Đình Tú",

    "Đức Anh",
    "Đức Dũng",
    "Đức Duy",
    "Đức Hải",
    "Đức Hiếu",
    "Đức Hoàng",
    "Đức Huy",
    "Đức Khang",
    "Đức Khải",
    "Đức Khôi",
    "Đức Long",
    "Đức Mạnh",
    "Đức Minh",
    "Đức Nam",
    "Đức Nguyên",
    "Đức Phát",
    "Đức Phúc",
    "Đức Quân",
    "Đức Thành",
    "Đức Thắng",
    "Đức Thiện",
    "Đức Thịnh",
    "Đức Trung",
    "Đức Tùng",
    "Đức Tuấn",

    "Duy Anh",
    "Duy Bách",
    "Duy Bảo",
    "Duy Đức",
    "Duy Hải",
    "Duy Hiếu",
    "Duy Hoàng",
    "Duy Hưng",
    "Duy Khang",
    "Duy Khánh",
    "Duy Khôi",
    "Duy Long",
    "Duy Minh",
    "Duy Nam",
    "Duy Phong",
    "Duy Phúc",
    "Duy Quân",
    "Duy Thành",
    "Duy Tùng",

    "Gia Bảo",
    "Gia Hưng",
    "Gia Huy",
    "Gia Khánh",
    "Gia Khiêm",
    "Gia Khang",
    "Gia Kiệt",
    "Gia Long",
    "Gia Minh",
    "Gia Nam",
    "Gia Nguyên",
    "Gia Phúc",
    "Gia Quân",
    "Gia Thành",

    "Hải Anh",
    "Hải Đăng",
    "Hải Dương",
    "Hải Long",
    "Hải Minh",
    "Hải Nam",
    "Hải Phong",
    "Hải Quân",
    "Hải Sơn",
    "Hải Trung",

    "Hoàng Anh",
    "Hoàng Bách",
    "Hoàng Duy",
    "Hoàng Hải",
    "Hoàng Huy",
    "Hoàng Khang",
    "Hoàng Khải",
    "Hoàng Khôi",
    "Hoàng Long",
    "Hoàng Minh",
    "Hoàng Nam",
    "Hoàng Phong",
    "Hoàng Phúc",
    "Hoàng Quân",
    "Hoàng Sơn",
    "Hoàng Trung",

    "Hữu Đạt",
    "Hữu Đức",
    "Hữu Hải",
    "Hữu Hiếu",
    "Hữu Hưng",
    "Hữu Khang",
    "Hữu Khánh",
    "Hữu Long",
    "Hữu Minh",
    "Hữu Nam",
    "Hữu Nghĩa",
    "Hữu Phát",
    "Hữu Phúc",
    "Hữu Thành",
    "Hữu Thắng",

    "Khánh Duy",
    "Khánh Hưng",
    "Khánh Khang",
    "Khánh Minh",
    "Khánh Nam",
    "Khánh Phong",
    "Khánh Toàn",

    "Minh Anh",
    "Minh Bách",
    "Minh Bảo",
    "Minh Đức",
    "Minh Duy",
    "Minh Hải",
    "Minh Hiếu",
    "Minh Hoàng",
    "Minh Hùng",
    "Minh Huy",
    "Minh Khang",
    "Minh Khánh",
    "Minh Khôi",
    "Minh Kiệt",
    "Minh Long",
    "Minh Nam",
    "Minh Nhật",
    "Minh Phát",
    "Minh Phong",
    "Minh Phúc",
    "Minh Quân",
    "Minh Quang",
    "Minh Thành",
    "Minh Thiện",
    "Minh Thịnh",
    "Minh Trí",
    "Minh Trung",
    "Minh Tú",
    "Minh Tuấn",

    "Nhật Anh",
    "Nhật Duy",
    "Nhật Hào",
    "Nhật Huy",
    "Nhật Khang",
    "Nhật Khôi",
    "Nhật Minh",
    "Nhật Nam",
    "Nhật Phong",
    "Nhật Quang",
    "Nhật Trung",

    "Phúc An",
    "Phúc Anh",
    "Phúc Hưng",
    "Phúc Khang",
    "Phúc Lâm",
    "Phúc Long",
    "Phúc Minh",
    "Phúc Nguyên",
    "Phúc Thịnh",

    "Quang Anh",
    "Quang Đức",
    "Quang Hải",
    "Quang Hiếu",
    "Quang Huy",
    "Quang Khải",
    "Quang Minh",
    "Quang Nam",
    "Quang Phúc",
    "Quang Thành",
    "Quang Trung",
    "Quang Vinh",

    "Quốc Anh",
    "Quốc Bảo",
    "Quốc Đạt",
    "Quốc Đức",
    "Quốc Huy",
    "Quốc Khánh",
    "Quốc Khang",
    "Quốc Minh",
    "Quốc Nam",
    "Quốc Phong",
    "Quốc Thịnh",
    "Quốc Trung",
    "Quốc Việt",

    "Thanh Bình",
    "Thanh Duy",
    "Thanh Hải",
    "Thanh Hùng",
    "Thanh Long",
    "Thanh Phong",
    "Thanh Sơn",
    "Thanh Tùng",

    "Thiên Ân",
    "Thiên Bảo",
    "Thiên Đức",
    "Thiên Khang",
    "Thiên Khôi",
    "Thiên Long",
    "Thiên Minh",
    "Thiên Phúc",
    "Thiên Quân",

    "Trọng Đức",
    "Trọng Hiếu",
    "Trọng Nghĩa",
    "Trọng Nhân",
    "Trọng Tấn",
    "Trọng Thành",

    "Tuấn Anh",
    "Tuấn Dũng",
    "Tuấn Hưng",
    "Tuấn Khang",
    "Tuấn Kiệt",
    "Tuấn Minh",
    "Tuấn Phong",
    "Tuấn Tú",

    # ========================================================
    # NỮ - TÊN ĐƠN
    # ========================================================

    "An", "Anh", "Ánh", "Bích", "Cẩm", "Châu", "Chi", "Đan", "Đào", "Diễm",
    "Diệp", "Dung", "Duyên", "Giang", "Hà", "Hân", "Hằng", "Hạnh", "Hiền",
    "Hoa", "Hoài", "Hồng", "Huệ", "Hương", "Huyền", "Khánh", "Khuê",
    "Kiều", "Lam", "Lan", "Lệ", "Liên", "Linh", "Loan", "Ly", "Mai", "Mẫn",
    "Mi", "Minh", "Mỹ", "My", "Na", "Nga", "Ngân", "Ngọc", "Nhã", "Nhi",
    "Nhung", "Oanh", "Phương", "Quyên", "Quỳnh", "San", "Tâm", "Thanh",
    "Thảo", "Thi", "Thư", "Thu", "Thúy", "Thùy", "Thy", "Tiên", "Trâm",
    "Trang", "Trinh", "Trúc", "Tú", "Tuyết", "Uyên", "Vân", "Vi", "Vy",
    "Xuân", "Yên", "Yến",

    # ========================================================
    # NỮ - TÊN KÉP
    # ========================================================

    "Ái Linh",
    "Ái My",
    "Ái Nhi",
    "Ái Vy",

    "Ánh Dương",
    "Ánh Hồng",
    "Ánh Mai",
    "Ánh Ngọc",
    "Ánh Tuyết",

    "Bảo An",
    "Bảo Anh",
    "Bảo Châu",
    "Bảo Hân",
    "Bảo Linh",
    "Bảo My",
    "Bảo Ngân",
    "Bảo Ngọc",
    "Bảo Nhi",
    "Bảo Trâm",
    "Bảo Vy",

    "Bích Hạnh",
    "Bích Hồng",
    "Bích Ngọc",
    "Bích Phương",
    "Bích Thảo",
    "Bích Trâm",

    "Cẩm Anh",
    "Cẩm Giang",
    "Cẩm Linh",
    "Cẩm Ly",
    "Cẩm Nhung",
    "Cẩm Tú",
    "Cẩm Vân",

    "Diệu Anh",
    "Diệu Hương",
    "Diệu Linh",
    "Diệu My",
    "Diệu Ngọc",
    "Diệu Nhi",
    "Diệu Thảo",

    "Gia An",
    "Gia Hân",
    "Gia Linh",
    "Gia My",
    "Gia Nghi",
    "Gia Nhi",
    "Gia Vy",

    "Hải Anh",
    "Hải Châu",
    "Hải Hà",
    "Hải My",
    "Hải Yến",

    "Hoài An",
    "Hoài Anh",
    "Hoài Hương",
    "Hoài Linh",
    "Hoài My",
    "Hoài Phương",
    "Hoài Thương",
    "Hoài Trang",

    "Hồng Anh",
    "Hồng Hạnh",
    "Hồng Hoa",
    "Hồng Loan",
    "Hồng Nhung",
    "Hồng Phúc",
    "Hồng Thắm",
    "Hồng Vân",

    "Huyền Anh",
    "Huyền Linh",
    "Huyền My",
    "Huyền Trang",
    "Huyền Trâm",

    "Khánh An",
    "Khánh Chi",
    "Khánh Hân",
    "Khánh Linh",
    "Khánh Ly",
    "Khánh My",
    "Khánh Ngân",
    "Khánh Ngọc",
    "Khánh Vy",

    "Kim Anh",
    "Kim Chi",
    "Kim Dung",
    "Kim Hạnh",
    "Kim Ngân",
    "Kim Ngọc",
    "Kim Oanh",
    "Kim Phượng",
    "Kim Thoa",

    "Lan Anh",
    "Lan Chi",
    "Lan Hương",
    "Lan Ngọc",
    "Lan Phương",
    "Lan Vy",

    "Mai Anh",
    "Mai Chi",
    "Mai Hương",
    "Mai Lan",
    "Mai Linh",
    "Mai Ly",
    "Mai Phương",
    "Mai Trang",

    "Minh Anh",
    "Minh Châu",
    "Minh Hà",
    "Minh Hằng",
    "Minh Hạnh",
    "Minh Ngọc",
    "Minh Phương",
    "Minh Tâm",
    "Minh Thư",
    "Minh Trang",

    "Mỹ Anh",
    "Mỹ Dung",
    "Mỹ Duyên",
    "Mỹ Hạnh",
    "Mỹ Linh",
    "Mỹ Ngọc",
    "Mỹ Phương",
    "Mỹ Tâm",
    "Mỹ Tiên",

    "Ngọc Anh",
    "Ngọc Ánh",
    "Ngọc Bích",
    "Ngọc Châu",
    "Ngọc Diệp",
    "Ngọc Dung",
    "Ngọc Hà",
    "Ngọc Hân",
    "Ngọc Hương",
    "Ngọc Lan",
    "Ngọc Linh",
    "Ngọc Mai",
    "Ngọc Minh",
    "Ngọc My",
    "Ngọc Nga",
    "Ngọc Ngân",
    "Ngọc Nhi",
    "Ngọc Phương",
    "Ngọc Quỳnh",
    "Ngọc Thảo",
    "Ngọc Trâm",
    "Ngọc Trang",
    "Ngọc Trinh",
    "Ngọc Tú",
    "Ngọc Vy",
    "Ngọc Yến",

    "Nhã Anh",
    "Nhã Linh",
    "Nhã Phương",
    "Nhã Uyên",

    "Phương Anh",
    "Phương Chi",
    "Phương Hà",
    "Phương Hạnh",
    "Phương Linh",
    "Phương Mai",
    "Phương My",
    "Phương Nhi",
    "Phương Thảo",
    "Phương Thanh",
    "Phương Trang",
    "Phương Uyên",

    "Quỳnh Anh",
    "Quỳnh Chi",
    "Quỳnh Hương",
    "Quỳnh Mai",
    "Quỳnh Nga",
    "Quỳnh Như",
    "Quỳnh Trang",

    "Thanh An",
    "Thanh Hà",
    "Thanh Hằng",
    "Thanh Hương",
    "Thanh Mai",
    "Thanh Ngân",
    "Thanh Thảo",
    "Thanh Trúc",
    "Thanh Vân",

    "Thảo Anh",
    "Thảo Linh",
    "Thảo My",
    "Thảo Nhi",
    "Thảo Nguyên",
    "Thảo Trang",
    "Thảo Vy",

    "Thu Anh",
    "Thu Hà",
    "Thu Hằng",
    "Thu Hiền",
    "Thu Hoài",
    "Thu Hương",
    "Thu Ngân",
    "Thu Phương",
    "Thu Thảo",
    "Thu Trang",

    "Thùy Anh",
    "Thùy Dung",
    "Thùy Dương",
    "Thùy Linh",
    "Thùy My",
    "Thùy Trang",
    "Thùy Trâm",

    "Trúc Anh",
    "Trúc Giang",
    "Trúc Linh",
    "Trúc Ly",
    "Trúc Mai",
    "Trúc Phương",

    "Tường An",
    "Tường Vy",

    "Tú Anh",
    "Tú Linh",
    "Tú Uyên",

    "Uyên Nhi",
    "Uyên Phương",
    "Uyên Thư",

    "Yến Anh",
    "Yến Linh",
    "Yến Nhi",
    "Yến Phương",
    "Yến Trang",

    # ========================================================
    # BỔ SUNG TÊN 2 ÂM TIẾT DÙNG ĐƯỢC CHO CẢ NAM/NỮ
    # ========================================================

    "An Bình",
    "An Khang",
    "An Minh",
    "An Nhiên",
    "An Phúc",
    "An Vy",

    "Bình An",
    "Bình Minh",
    "Bình Nguyên",

    "Hà Anh",
    "Hà Linh",
    "Hà My",
    "Hà Phương",
    "Hà Vy",

    "Khánh An",
    "Khánh Anh",
    "Khánh Hòa",
    "Khánh Minh",

    "Minh An",
    "Minh Châu",
    "Minh Khang",
    "Minh Khôi",
    "Minh Ngọc",

    "Nhật Anh",
    "Nhật Hạ",
    "Nhật Minh",

    "Thiên An",
    "Thiên Ân",
    "Thiên Hà",
    "Thiên Hương",
    "Thiên Kim",
    "Thiên Ngân",
    "Thiên Thanh",
    "Thiên Trang",
]


class ModelAi:
    def __init__(self, api_key: str = "", base_url: str = "https://api1.shupremium.com/v1", model: str = "gpt-4o-mini"):
        self.api_key = api_key.strip() if api_key else ""
        self.base_url = base_url.rstrip("/") if base_url else "https://api1.shupremium.com/v1"
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
