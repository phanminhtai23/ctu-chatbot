# Design: CTU style (cho FE)

Nguồn: khảo sát trực tiếp https://www.ctu.edu.vn/ (homepage chính thức, theme Joomla "tz_varaham") ngày 2026-10-04. Màu lấy từ CSS thật của site (`compiled-*.css`), không phải đoán.

## Logo

- Huy hiệu hình thoi (diamond badge): viền xanh cyan → nền xanh navy đậm bên trong → bánh răng (gear) màu vàng/gold bao quanh ngọn đuốc đỏ có trang sách trắng bên dưới → chữ "ĐẠI HỌC CẦN THƠ" màu trắng chạy theo viền trong.
- File gốc: `https://www.ctu.edu.vn/images/upload/logo.png` (desktop), có bản `logomobile.png` và `logo-mobile-d.png` (sticky/dark) riêng — tức họ có logo biến thể cho dark background.
- Trên header: logo desktop cao 120px, logo sticky-header cao 75px.

## Bảng màu (lấy từ CSS thật)

| Vai trò | Hex | Dùng ở đâu trên site gốc |
|---|---|---|
| Navy chính (header sticky, nền thương hiệu) | `#0D47A1` | `#astroid-sticky-header` background |
| Navy đậm (footer) | `#0E346F` | nền footer |
| Cyan/sky blue (viền logo, icon) | `#22B8F0` / `#00AEEF` / `#00AFEF` | viền huy hiệu, icon/accent rải rác trong trang |
| Link blue | `#077FE4` | màu link mặc định trong nội dung |
| Link blue hover | `#0F6ECD` | hover link |
| Nav active blue | `#033EB6` | trạng thái active của menu |
| Gold/vàng accent | `#FFF201` (hover chữ trên header sticky) và `#FBC500` (breadcrumb active) | hover/active trên nền navy — tương phản mạnh, giống màu bánh răng trong logo |
| Light blue hover (footer) | `#5BBBFF` | hover link trong footer |
| Đỏ (ngọn đuốc trong logo, dùng rất hiếm trên UI) | `#A8171C` / `#F70004` | chỉ thấy trong logo, gần như không dùng cho UI thường |
| Heading text | `#132C33` | màu chữ h1–h6, gần đen nhưng ngả xanh |
| Body text | `#666666` | màu chữ thường |
| Nền trang | `#FFFFFF` / `#FEFFFE` | background chính |

**Tóm tắt rule phối màu:** nền navy (`#0D47A1`/`#0E346F`) dùng cho header/footer với chữ trắng, hover/active trên nền navy chuyển sang vàng (`#FFF201`/`#FBC500`) — không dùng xanh dương trên nền xanh dương. Trên nền trắng thì dùng link blue (`#077FE4`) là màu nhấn chính.

## Typography

- Font chính: **Readex Pro** (Google Font) — toàn bộ body, heading, nav đều dùng font này (`font-family: Readex Pro` trong CSS compiled).
- Heading: weight 600, body: weight 300 — tương phản đậm/nhạt rõ giữa heading và nội dung.
- Cỡ chữ heading (desktop): h1 `3em`, h2 `2em`, h3 `1.8em`, h4 `1.6em`, h6 `1.2em`; line-height heading ~1.1–1.2em, body line-height `1.7em`.
- Ghi chú: một vài block page-builder riêng lẻ trong trang dùng font `K2D` (không phải font chủ đạo, chỉ xuất hiện cục bộ) — có thể bỏ qua, không cần theo.

## Layout / UI patterns

- Header: sticky, nền navy, logo bên trái, menu ngang bên phải, chữ trắng → vàng khi hover/active. Có toggle ngôn ngữ (EN) góc phải trên cùng.
- Hero: carousel/slider ảnh lớn ngay dưới header, có nút điều hướng trái/phải, thường là ảnh sự kiện + caption.
- Nội dung: bố cục dạng card cho tin tức (ảnh + tiêu đề + mô tả ngắn), có section thống kê (số liệu lớn: số sinh viên, nhà nghiên cứu, công bố...).
- Footer: nền navy đậm hơn header, chữ trắng/xám nhạt, chia cột: liên hệ, mạng xã hội, dịch vụ nội bộ (email, LMS...), thông tin công khai.
- Phong cách chung: trang trọng, học thuật, kiểu website cơ quan nhà nước/trường công — không dùng màu mè, bo góc nhẹ, nhiều khoảng trắng, nhấn bằng navy + vàng.

## Gợi ý áp dụng cho FE (Tailwind)

Khi implement, map palette trên vào Tailwind theme thay vì hardcode hex rải rác:

```js
// tailwind.config.js (gợi ý, chưa áp dụng)
colors: {
  'ctu-navy': '#0D47A1',
  'ctu-navy-dark': '#0E346F',
  'ctu-cyan': '#22B8F0',
  'ctu-link': '#077FE4',
  'ctu-link-hover': '#0F6ECD',
  'ctu-gold': '#FFF201',
  'ctu-gold-active': '#FBC500',
  'ctu-heading': '#132C33',
  'ctu-body': '#666666',
}
```

- Header/footer app nên dùng `ctu-navy`/`ctu-navy-dark` với chữ trắng, hover/active dùng `ctu-gold`.
- Nội dung chính nền trắng, link dùng `ctu-link`/`ctu-link-hover`.
- Font: thêm Google Font `Readex Pro` vào `index.html`/`index.css`, set làm font mặc định thay vì `system-ui`.
- Không bắt buộc sao chép y hệt 100% — đây là tài liệu tham khảo để giữ "tinh thần CTU" (navy + vàng + trang trọng), không phải brand guideline chính thức của trường.
