# Feature: admin-router-prompt-assist

- **Status:** done (FE + BE; không cần DB: prompt nằm trong `vector-docs/routes.json`)
- **Scope:** FE, BE
- **Yêu cầu từ user (2026-11-08):** nhập mô tả tài liệu mới, nhờ LLM đọc prompt phân loại cũ cùng dữ liệu mới rồi viết lại; hiện so sánh bản mới và bản cũ; admin có thể từ chối, phản hồi để sinh lại hoặc đồng ý.

## Luồng
1. Trong tab **Tài liệu** (`/admin/documents`), bấm nút lấp lánh trên thẻ tài liệu → hộp thoại `components/admin/RouterPromptAssist.tsx`.
2. Admin nhập mô tả (điền sẵn từ mô tả đang lưu) → **Tạo đề xuất**.
3. BE `POST /admin/documents/catalog/router-prompt/proposals` `{route_id, description, feedback?, previous?}`: `app/services/ingest/router_prompt.py` gửi cho LLM prompt phân loại hiện tại (`router_prompt`), mọi tuyến khác đang có (id, tên, prompt, số quyết định, mô tả), tuyến tài liệu cần viết lại và mô tả admin nhập. LLM trả JSON `{router_prompt, node_prompt, changes[]}`. **Không lưu gì.**
4. FE hiện so sánh theo từ (`lib/textDiff.ts`, LCS): cột "Đang dùng" gạch đỏ phần bỏ, cột "Đề xuất" tô xanh phần thêm, cho cả prompt của tuyến tài liệu lẫn prompt phân loại chung; kèm lời giải thích thay đổi của AI.
5. Ba lựa chọn: **Đồng ý và lưu** (`POST .../router-prompt/apply` ghi `router_prompt` chung + prompt của tuyến cho mọi version cùng tài liệu + mô tả), **Từ chối** (đóng, bỏ đề xuất), hoặc nhập **phản hồi** → **Gửi phản hồi và tạo lại** (gửi kèm bản đề xuất trước và phản hồi, có thể lặp nhiều lần).

## Notes
- Đề xuất sai định dạng (không phải JSON hợp lệ, rỗng, quá dài: router > 8000, tuyến > 4000 ký tự) bị chặn 422 `PROPOSAL_INVALID`. Lỗi LLM: 503 `LLM_NOT_CONFIGURED` / `LLM_UNAVAILABLE`, 502 `PROPOSAL_FAILED`. Apply cần catalog ghi được (`CATALOG_READ_ONLY` ở production).
- `app.state.llm` (GeminiClient dùng chung với luồng chat) + dependency `get_llm`.
- Prompt phân loại thực tế = `router_prompt` + danh sách `- id: tên. prompt` của các tuyến ĐANG BẬT (xem `scope.classify`); các luật chạy trước LLM (chào hỏi, nhắc "Điều N", file đính kèm, kiến thức bổ sung điểm cao) bỏ qua prompt này.
- Test: `tests/test_router_prompt.py`.
