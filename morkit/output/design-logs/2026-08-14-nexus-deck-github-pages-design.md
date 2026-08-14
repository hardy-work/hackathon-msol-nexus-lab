# Design Log — Live view cho Nexus Agent Deck trên GitHub Pages

**Date:** 2026-08-14
**Topic:** Publish `~/Downloads/Nexus Agent` lên GitHub Pages, index là `AI Agent Deck.dc.html`
**Mode:** brainstorming (explore only — chưa implement)

---

## 1. Problem framing

Cần một live view public cho deck trình bày Nexus Agent, để chia sẻ bằng URL thay vì gửi file.

Giả định ban đầu (sai): deck là một file HTML standalone, chỉ cần upload lên Pages là xong.

Thực tế sau khi khảo sát folder (119 file, 81 MB):

- `AI Agent Deck.dc.html` (66 KB) **không self-contained**. Nó là gốc của một cây phụ thuộc relative-path gồm JS runtime, design-system bundle, ảnh, video, và 4 sub-deck lồng trong `<iframe>`.
- Folder chứa lẫn lộn file production và file rác: 7 bản backup/standalone của chính deck (~11 MB), media trùng lặp (bản hashed + bản không hashed), screenshot, `.md` brief, `.DS_Store`.
- Folder **chưa phải git repo**.

Nên bài toán thật sự không phải "upload 1 file", mà là: **xác định đúng closure phụ thuộc, loại phần thừa, rồi deploy sao cho GitHub Pages không phá vỡ closure đó.**

---

## 2. Approaches considered

### 2.1 Nơi host

| Option | Ưu | Nhược |
|---|---|---|
| **A. Repo riêng `hardy-work/nexus-agent-deck`** | Tách hẳn media 49 MB khỏi repo code; URL sạch; xoá được độc lập | Thêm 1 repo phải quản |
| B. `gh-pages` orphan branch trong repo hiện tại | `main` sạch working tree | Blob vẫn nằm trong history repo code; 2 branch phải nhớ |
| C. `docs/` trong `main` | Thao tác đơn giản nhất | Mọi clone repo code kéo thêm 49 MB |
| D. GitHub Actions `upload-pages-artifact` | Không branch rác | Phức tạp nhất, cần workflow |

### 2.2 Xử lý tên file index

`AI Agent Deck.dc.html` có khoảng trắng + double-extension; Pages cần `index.html`.

- **Copy → `index.html`**: giữ tên gốc, thêm bản copy. Có 2 bản phải sync.
- Rename → `index.html`: sạch nhất, nhưng lệch tên với bản local.
- Stub redirect: giữ nguyên tên gốc, URL cuối có `%20`, thêm 1 hop.

### 2.3 Scope publish

- **Slim** (chỉ closure thật sự): 37 file, ~49 MB.
- Nguyên folder: 119 file, 81 MB — rủi ro thiếu file thấp nhất nhưng repo nặng vĩnh viễn.

### 2.4 Video (43 MB / 4 file)

- **Commit thẳng**: dưới giới hạn GitHub (100 MB/file, ~1 GB soft/repo), chất lượng nguyên vẹn.
- Nén ffmpeg CRF23: ước tính còn ~10 MB, nhưng cần review chất lượng.
- Bỏ hẳn: repo ~6 MB, nhưng slide demo trống.

---

## 3. Decisions

| # | Quyết định | Lý do |
|---|---|---|
| D1 | Repo riêng **`hardy-work/nexus-agent-deck`** | Không để 49 MB media dính vào history của repo code |
| D2 | Publish bản **slim** (37 file, ~49 MB) | Bỏ 11 MB backup deck + ~30 file không được reference, không mất gì cho live view |
| D3 | **Copy** deck thành `index.html`, giữ nguyên file gốc | Tên local không đổi; việc copy nằm trong script deploy |
| D4 | **Commit video nguyên bản**, không nén | Trong giới hạn GitHub; ưu tiên chất lượng demo |
| D5 | **Serve local + verify trước khi push** | Bắt lỗi thiếu file trước khi blob vào git history vĩnh viễn |
| D6 | Bắt buộc có file `.nojekyll` ở gốc Pages | Xem F1 dưới |

---

## 4. Findings — 4 cạm bẫy đã xác định (verified)

**F1 — Jekyll ăn mất `_ds/` (nghiêm trọng nhất).**
GitHub Pages mặc định chạy Jekyll, bỏ qua mọi file/folder bắt đầu bằng `_`. Deck load `./_ds/industry-20f39a08-.../styles.css` và `_ds_bundle.js` → cả hai trả 404 → deck render nhưng mất toàn bộ style và runtime. Fix: file rỗng `.nojekyll` ở gốc. (`.nojekyll` cũng cần thiết để dotfile `.image-slots.state.json` được serve — xem F3.)

**F2 — Reference không chỉ nằm ở `src=`/`href=`.**
Deck dùng custom element `<x-import from="...">`. Regex chỉ quét `src`/`href` bỏ sót:
- `AI Agent Deck.dc.html:406` → `<x-import from="./deck-stage.js">` (135 KB)
- `uploads/llm-wiki/nap-tri-thuc.dc.html` → `<x-import from="./wiki-static.jsx">`

**F3 — `.image-slots.state.json` là sidecar runtime, không phải file tạm.**
`image-slot.js:174` gọi `fetch('.image-slots.state.json')` **lúc render** để hydrate ảnh vào từng slot (267 KB). Bỏ đi → các ô ảnh hiện trống, **không có lỗi nào báo ra**. Loại bug chỉ lộ sau deploy.

**F4 — Case-sensitivity.**
macOS case-insensitive, Pages thì không. `uploads/` đang có cả `Agent Orchestration.jpg` lẫn `agent-orchestration.png`. Deck ref bản lowercase nên hiện tại ổn, nhưng cần verify link sau khi lên.

**Tin tốt:** 4 nested deck trong iframe (`kien-truc-tong-the`, `nap-tri-thuc`, `to-chuc-tri-thuc`, `truy-xuat-du-lieu`) **self-contained** — inline `<style>`, 0 tham chiếu `_ds/`. Cả cây `uploads/llm-wiki/` rút xuống 6 file.

---

## 5. Slim manifest (37 file, ~49 MB)

```
/
  index.html                 ← copy của AI Agent Deck.dc.html
  AI Agent Deck.dc.html         68K
  .nojekyll                     NEW — bắt buộc (F1)
  deck-stage.js                135K   (F2)
  image-slot.js                 64K
  support.js                    68K
  .image-slots.state.json      267K   (F3)
  h3kp6lpjoe5t2jhcslxsowx9lxk8adk9jiraengo-msrokfp3-4s1q.png   944K
  mot-pm-chuyen-nghiep-can-thuc-hien-lap-k-msrneunb-9f41.jpg    48K
  product-manager-msro590o-gz9u.webp                            72K
  _ds/industry-20f39a08-3061-48e6-a859-56db016d2655/            36K

/assets
  nexus-avatar.png                                             1.1M

/uploads
  agent-orchestration.png      1.4M
  multi-tenant.png             1.7M
  summary-evidence.mp4          18M
  meeting-notes-a958a123.mp4    16M
  daily-repor-risk-assessment.mp4          5.4M
  reminder-update-log-task-8dbe70f2.mp4    3.7M

/uploads/llm-wiki
  kien-truc-tong-the.dc.html    12K
  nap-tri-thuc.dc.html         4.0K
  to-chuc-tri-thuc.dc.html      28K
  truy-xuat-du-lieu.dc.html     24K
  support.js                    68K
  wiki-static.jsx                      (F2)
```

**Loại bỏ (82 file, ~32 MB):** 7 backup deck (`AI Agent Deck (light backup|test-fix|standalone-src|standalone-src v2)`, `Nexus Agent Deck (standalone-src)`, `NexusBot Deck (standalone)`, `NexusBot Deck (standalone) v2`) · `animations-v3.jsx` · `scene-chuan-hoa.jsx` · `tweaks-panel.jsx` · `project-manager-pm-1-msro2u8t-qbvu.jpeg` · `export/` · `screenshots/` · `.DS_Store` · `.thumbnail` · ~30 file không được reference trong `uploads/` (mp4 trùng, screenshot, `.md` brief, deck rời) · phần còn lại của `uploads/llm-wiki/`.

---

## 6. Open questions

**Q1 — Repo phải public.** GitHub Pages trên private repo yêu cầu gói trả phí (Pro/Team). Nếu `nexus-agent-deck` để private mà không có gói, Pages sẽ không bật được. Nghĩa là: toàn bộ nội dung deck — video meeting notes, kiến trúc multi-tenant, use case PM Agent — sẽ **public với bất kỳ ai có URL**. Cần confirm rõ trước khi push, vì sau khi push thì nội dung coi như đã phát tán.

**Q2 — Quy trình cập nhật deck về sau.** Sửa deck ở `~/Downloads/Nexus Agent` rồi sync sang repo bằng cách nào? Script `rsync` theo manifest, hay copy tay? Liên quan tới D3 (bản `index.html` copy phải được regenerate mỗi lần).

**Q3 — Font Google.** Deck load `fonts.googleapis.com`. Trên Pages (HTTPS) chạy bình thường, nhưng là external dependency — nếu muốn hoàn toàn offline/self-contained thì phải inline font.

**Q4 — `support.js` gọi `fetch(location.href)`.** Chưa xác định feature này làm gì. Trên Pages (same-origin, HTTPS) về nguyên tắc chạy được, nhưng cần quan sát console lúc verify local (D5).

---

## 7. Next step

Chạy `/morkit:propose nexus-deck-github-pages` để sinh proposal + design + tasks.

Luồng implement dự kiến:
1. Confirm Q1 (repo public → deck public).
2. Dựng staging folder theo slim manifest, thêm `.nojekyll` + `index.html`.
3. Serve local (`python3 -m http.server`), verify: console 0 lỗi 404 · 4 iframe render · 4 video play · image slot có ảnh (F3) · style đúng (F1).
4. `git init` + commit + tạo repo `hardy-work/nexus-agent-deck` + push.
5. Bật Pages (source: `main` / root).
6. Verify lại trên URL live — đặc biệt case-sensitivity (F4).
