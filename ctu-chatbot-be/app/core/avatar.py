"""Ảnh đại diện mặc định ngẫu nhiên cho người dùng chưa tải ảnh riêng.

Dùng DiceBear, kiểu "thumbs" (mặt ngố ngố đáng yêu, giấy phép CC0 nên không cần ghi công). Ảnh SVG được tạo theo `seed` ở máy chủ
DiceBear, mình chỉ lưu đường dẫn, không tốn dung lượng.
"""

import secrets

STYLE = "thumbs"


def default_avatar_url(seed: str) -> str:
    return f"https://api.dicebear.com/9.x/{STYLE}/svg?seed={seed}"


def random_avatar_url() -> str:
    return default_avatar_url(secrets.token_hex(6))
