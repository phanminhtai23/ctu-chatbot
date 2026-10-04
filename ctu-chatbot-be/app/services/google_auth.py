from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings


class GoogleAuthError(Exception):
    """Token Google không hợp lệ hoặc chưa cấu hình."""


@dataclass
class GoogleIdentity:
    email: str
    name: str
    picture: str | None


def verify_google_id_token(credential: str) -> GoogleIdentity:
    """Xác thực Google ID token (JWT) do nút "Sign in with Google" trả về.

    Kiểm tra chữ ký, hạn dùng, `aud` = GOOGLE_CLIENT_ID và email đã được Google xác minh.
    """
    if not settings.google_client_id:
        raise GoogleAuthError("Google login is not configured")
    try:
        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        raise GoogleAuthError("Invalid Google token") from exc

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise GoogleAuthError("Google email is not verified")
    return GoogleIdentity(
        email=email.lower(),
        name=claims.get("name") or email.split("@")[0],
        picture=claims.get("picture"),
    )
