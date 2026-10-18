"""Gọi Gemini đọc ảnh trang: chép chữ (OCR) và khoanh vị trí từng Điều. Xoay nhiều API key khi bị 429."""

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Protocol

from app.core.config import settings
from app.services.llm.key_pool import KeyPool

logger = logging.getLogger("app.ingest")

OCR_PROMPT = """Đây là các trang ảnh (scan) của một văn bản quy định tiếng Việt, theo thứ tự: trang {pages}.
Hãy chép lại CHÍNH XÁC toàn bộ chữ trên từng trang.
- Trước nội dung mỗi trang ghi một dòng riêng đúng dạng `--- Trang N ---` (N là số trang ở trên).
- Giữ nguyên từng đoạn, từng khoản (1., 2., a), b)...), mỗi đoạn một dòng. Tiêu đề "Chương ..." và "Điều N. ..." nằm ở dòng riêng.
- Bảng: viết dạng Markdown (| cột 1 | cột 2 |, kèm dòng | --- | --- |). Công thức: viết bằng chữ và ký hiệu thường, KHÔNG dùng LaTeX.
- Giữ cả số trang nếu có. Không tóm tắt, không bình luận, không thêm ``` hay lời dẫn."""

LOCATE_PROMPT = """Đây là trang {page} của văn bản "Quy định công tác học vụ" (tiếng Việt, bản scan).
Hãy xác định MỌI khối văn bản trên trang theo thứ tự đọc: tiêu đề "Điều N. ...", từng đoạn văn, từng khoản (1., 2., a), b)...), và từng bảng.
Với mỗi khối trả về:
- "box_2d": [ymin, xmin, ymax, xmax] chuẩn hoá về 0-1000, ôm sát khối chữ.
- "article": số N của "Điều N." mà khối đó thuộc về. Khối thuộc Điều gần nhất phía trên nó. Các khối nằm đầu trang, trước mọi tiêu đề "Điều", là phần tiếp theo của Điều {previous}.
Quy tắc:
- Bỏ qua số trang, dòng đầu/cuối trang, tiêu đề "Chương ..." (article = null).
- Mỗi khoản/đoạn là một khối riêng; một bảng là một khối.
- KHÔNG chép lại nội dung chữ.
Chỉ trả JSON: {{"blocks": [{{"article": 12, "box_2d": [ymin, xmin, ymax, xmax]}}, ...]}}"""


class VisionError(Exception):
    """Gemini không đọc được ảnh (hết hạn mức ở mọi key, lỗi mạng kéo dài, phản hồi hỏng...)."""


class VisionBlocked(VisionError):
    """Gemini trả rỗng / bị chặn (thường là bộ lọc trích dẫn nguyên văn khi gửi nhiều trang một lúc)."""


class Vision(Protocol):
    def ocr(self, images: list[bytes], page_numbers: list[int]) -> str: ...

    def locate(self, image: bytes, page: int, previous_article: int | None) -> list[dict]: ...


def _classify(exc: BaseException) -> str:
    text = str(exc).lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429 or "429" in text or "resource_exhausted" in text or "quota" in text:
        return "rate_limited"
    if code in (401, 403) or "api key not valid" in text or "permission_denied" in text:
        return "invalid_key"
    if code in (500, 502, 503, 504) or "503" in text or "unavailable" in text or "overloaded" in text or "timed out" in text:
        return "transient"
    return "other"


class GeminiVision:
    def __init__(
        self,
        keys: list[str],
        model: str,
        interval: float = 0.0,
        client_factory: Callable[[str], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._pool = KeyPool([k for k in dict.fromkeys(keys) if k])
        self._model = model
        self._interval = interval
        self._sleep = sleep
        self._factory = client_factory or self._default_client
        self._clients: dict[int, object] = {}
        self._last_call = 0.0

    @staticmethod
    def _default_client(key: str):
        from google import genai
        from google.genai import types

        return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=180_000))

    @classmethod
    def from_settings(cls) -> "GeminiVision":
        return cls(settings.gemini_api_keys, settings.ingest_model, settings.ingest_call_interval_seconds)

    def _generate(self, contents: list, json_mode: bool) -> str:
        from google.genai import types

        if len(self._pool) == 0:
            raise VisionError("Chưa có GEMINI_API_KEY_* trong .env")
        config = types.GenerateContentConfig(
            temperature=0, response_mime_type="application/json" if json_mode else None
        )
        last_error = ""
        for attempt in range(4):
            transient = False
            candidates = list(self._pool.candidates())
            if not candidates:  # mọi key đang nghỉ: chờ key sớm nhất dùng lại được
                self._sleep(min(30.0, self._pool.seconds_until_available() + 1))
                continue
            for idx, key in candidates:
                wait = self._interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    self._sleep(wait)
                client = self._clients.setdefault(idx, self._factory(key))
                self._last_call = time.monotonic()
                try:
                    response = client.models.generate_content(model=self._model, contents=contents, config=config)
                except Exception as exc:  # noqa: BLE001
                    kind = _classify(exc)
                    last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                    if kind == "rate_limited":
                        logger.warning("Gemini key #%d hết hạn mức, đổi key", idx + 1)
                        self._pool.block(idx, 60)
                        continue
                    if kind == "invalid_key":
                        self._pool.block(idx, 3600)
                        continue
                    if kind == "transient":
                        transient = True
                        break
                    raise VisionError(last_error) from exc
                self._pool.mark_ok(idx)
                text = getattr(response, "text", None) or ""
                if not text.strip():
                    raise VisionBlocked("Gemini trả về rỗng (có thể bị chặn nội dung)")
                return text
            if transient:
                self._sleep(5 * (attempt + 1))
        raise VisionError(f"Gemini không phản hồi sau nhiều lần thử: {last_error or 'mọi key đều hết hạn mức'}")

    def ocr(self, images: list[bytes], page_numbers: list[int]) -> str:
        from google.genai import types

        parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images]
        prompt = OCR_PROMPT.format(pages=", ".join(str(n) for n in page_numbers))
        return self._generate([*parts, prompt], json_mode=False)

    def locate(self, image: bytes, page: int, previous_article: int | None) -> list[dict]:
        from google.genai import types

        previous = previous_article if previous_article is not None else "(chưa có, trang đầu của Quy định)"
        text = self._generate(
            [types.Part.from_bytes(data=image, mime_type="image/jpeg"), LOCATE_PROMPT.format(page=page, previous=previous)],
            json_mode=True,
        )
        try:
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE))
        except ValueError as exc:
            raise VisionError(f"Phản hồi khoanh vùng trang {page} không phải JSON") from exc
        blocks = data.get("blocks") if isinstance(data, dict) else data
        return blocks if isinstance(blocks, list) else []
