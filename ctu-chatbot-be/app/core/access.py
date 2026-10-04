from app.core.config import settings


def is_domain_allowed(email: str) -> bool:
    """Email có thuộc tên miền được phép đăng nhập không (danh sách rỗng = cho tất cả)."""
    if not settings.allowed_email_domains:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    return any(domain == d or domain.endswith(f".{d}") for d in settings.allowed_email_domains)


def can_access(email: str, role: str) -> bool:
    """Admin được miễn giới hạn tên miền (để quản trị viên dùng Gmail cá nhân); user thường thì không."""
    return role == "admin" or is_domain_allowed(email)
