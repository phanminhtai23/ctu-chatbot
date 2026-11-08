# CTU Chatbot

Chatbot app giúp sinh viên CTU hỏi về quy chế công tác học vụ (cách tính điểm, tín chỉ, quy định học kỳ...) dựa trên văn bản quy định (`QD3266_...pdf`).

## Trước khi code — ĐỌC THỨ TỰ NÀY

1. `agent-docs/00-overview.md` — tech stack, tech flow, kiến trúc tổng thể.
2. `agent-docs/01-rules.md` — quy tắc code/test/cập nhật docs. Bắt buộc tuân theo.
3. `agent-docs/02-design-ctu-style.md` — bảng màu, font, logo, layout "CTU style" lấy từ ctu.edu.vn thật. BẮT BUỘC đọc trước khi code bất kỳ UI/component nào ở `ctu-chatbot-fe`.
4. `agent-docs/features/*.md` — mỗi file là 1 feature. Đọc file của feature đang đụng tới TRƯỚC khi sửa code liên quan.

## Quy tắc bắt buộc

- Mỗi lần bắt đầu/hoàn thành/thay đổi một feature → cập nhật đúng file trong `agent-docs/features/` (trường `status`, phần `Notes`). Không chỉ sửa code mà bỏ qua docs.
- Chỉ làm **1 feature/lần**, đủ cả FE + BE + DB cho feature đó trước khi sang feature khác (theo đúng brainstorm gốc).
- Không tự thêm feature ngoài danh sách trong `agent-docs/features/` mà không hỏi lại user trước.
- File gốc `brainstorm.txt` là nguồn ý tưởng ban đầu — nếu có mâu thuẫn với `agent-docs/`, ưu tiên `agent-docs/` vì đó là trạng thái đã được chốt/cập nhật.

## Tech stack (chi tiết xem `agent-docs/00-overview.md`)

- FE: React + Tailwind, CTU style (xem `agent-docs/02-design-ctu-style.md`)
- BE: FastAPI
- DB: PostgreSQL (deploy: Supabase)
- LLM: Gemini (free tier) + LangGraph
- Test: pytest, dùng DeepSeek chat API (local) để test
- Deploy: FE → Vercel, DB → Supabase
