# Landing assets

## Document search hero

- Implemented in `src/components/landing/DocumentSearchVisual.tsx` and `src/pages/Landing.css`.
- A native SVG illustration of a magnifying glass inspecting academic and dormitory regulations; no generated raster illustration or campus photo is used.
- Document labels and decision numbers come from the first two real documents in the public catalog API. A neutral placeholder is shown before catalog data is available.
- The glass lens and document highlights animate with CSS. Reduced-motion settings keep the illustration static.
- The illustration caption links to the complete supported-document list.
- Gradients and filter IDs are scoped with React `useId`.

## chat-reference-preview.webp

- Captured directly with Playwright from the running CTU Chatbot on 2026-11-21.
- Student question: “Mình mới vào năm nhất, học kỳ đầu có phải tự đăng ký môn không?” The user does not name an article or ask for a specific answer length; the chatbot independently cites Điều 13 and Điều 14.
- Shows the chat answer and original document reference panel for Điều 14 of QĐ 3266/QĐ-ĐHCT, with the relevant text highlighted.
- Screenshot is cropped to the chat and reference area, excluding the account identity and conversation list. No mock conversation or UI has been composited into the image.
- Encoded as WebP (quality 88); 1300 × 900.

No external image host is required at runtime. Re-capture the product screenshot when the chat/reference layout changes materially.
