# Review Checklist — nexus-deck-github-pages

**Human gate.** `/morkit:executing-plans` bị chặn cho tới khi mục cuối file này ghi `Overall Decision: OK`.

Reviewer: mor_tungdv (tungdau1510@gmail.com)
Ngày review: 2026-08-14

---

## A. Phạm vi & quyết định

- [x] **A1** — Đồng ý host ở **repo riêng** `hardy-work/nexus-agent-deck`, không phải trong `hackathon-msol-nexus-lab`.
- [x] **A2** — Đồng ý publish **bản slim** (26 file, 49 MB), chấp nhận 93 file bị loại theo `proposal.md` mục 5.
- [x] **A3** — Đồng ý **commit video nguyên bản** (43 MB / 4 file), hiểu rằng blob vào git history là vĩnh viễn.
- [x] **A4** — Đồng ý `index.html` là **bản copy** của `AI Agent Deck.dc.html` (2 file trùng nội dung trong repo).

## B. Rủi ro công khai (quan trọng nhất)

- [x] **B1** — Hiểu rằng repo **bắt buộc public** (Pages trên private repo cần gói trả phí).
- [x] **B2** — Đã xem lại nội dung 4 video sẽ public: `summary-evidence.mp4`, `meeting-notes-a958a123.mp4`, `daily-repor-risk-assessment.mp4`, `reminder-update-log-task-8dbe70f2.mp4` — **không chứa** thông tin khách hàng, credential, tên nhân sự nội bộ, hay dữ liệu không được phép phát tán.
- [x] **B3** — Đã xem lại 2 ảnh kiến trúc sẽ public: `uploads/multi-tenant.png`, `uploads/agent-orchestration.png`.
- [x] **B4** — Đã xem lại nội dung 4 sub-deck `uploads/llm-wiki/*.dc.html` và deck chính.
- [x] **B5** — Chấp nhận rằng sau khi push, nội dung coi như đã phát tán — xoá repo **không** thu hồi được.

> ⚠ B2–B4 là kiểm tra thủ công, không tự động hoá được. Đây là điểm không quay lại được của change này.

## C. Tính đúng đắn kỹ thuật

- [x] **C1** — Manifest 26 file đã được verify là closure đầy đủ (không thiếu file runtime).
- [x] **C2** — `.nojekyll` có trong kế hoạch và có verify riêng (task 2.2 + 5.3).
- [x] **C3** — `.image-slots.state.json` được giữ, và `.gitignore` không ignore nhầm nó (task 2.3).
- [x] **C4** — Gate verify-local đặt **trước** commit đầu tiên (Phase 3 → Phase 4).
- [x] **C5** — Folder nguồn `~/Downloads/Nexus Agent` được giữ read-only trong toàn bộ change.
- [x] **C6** — Có đường xử lý khi `gh repo create` fail vì quyền org (task 4.2), và không tự ý đổi owner.

## D. Sau khi deploy

- [x] **D1** — Quy trình update về sau (`sync.sh`) là chấp nhận được.
- [x] **D2** — Đồng ý bỏ qua các Open Question chưa xử lý: Q3 (Google Fonts vẫn load từ CDN), Q4 (`support.js` gọi `fetch(location.href)` — quan sát lúc verify).

---

## Ghi chú của reviewer

_(điền)_

---

## Overall Decision

```
Overall Decision: OK
```

> Đổi `PENDING` thành `OK` để mở khoá `/morkit:executing-plans`.
> Dùng `NEEDS_CHANGES` kèm ghi chú ở mục trên nếu cần sửa artifact trước.
