# Tasks — nexus-deck-github-pages

**Change:** `nexus-deck-github-pages`
**Created:** 2026-08-14
**Total tasks:** 24 (Phase 1: 4 · Phase 2: 4 · Phase 3: 8 · Phase 4: 3 · Phase 5: 5)
**Gate:** `review-checklist.md` phải có `Overall Decision: OK` trước khi chạy `/morkit:executing-plans`

**Biến dùng chung:**
```
SRC="/Users/tungdao/Downloads/Nexus Agent"
STG="/Users/tungdao/Desktop/nexus-agent-deck"
REPO="mor-tungdv/nexus-agent-deck"
```

**Nguyên tắc:** `$SRC` là read-only trong toàn bộ change. Mọi thao tác trên `$STG`.

---

## Phase 1 — Manifest & staging (verify-first)

- [x] **1.1 — Viết `manifest.txt` (danh sách 26 path tương đối cần copy)**
  Tạo `$STG/manifest.txt`, mỗi dòng 1 path tương đối so với `$SRC`. Nội dung lấy từ `proposal.md` mục 5 (không gồm `index.html` và `.nojekyll` — hai file đó được sinh ra, không copy).
  **Verify:** `wc -l < "$STG/manifest.txt"` trả về `26`.

- [x] **1.2 — Assert mọi path trong manifest tồn tại trong `$SRC` (chạy TRƯỚC khi copy)**
  Loop từng dòng manifest, `test -e "$SRC/$line"`, in ra path nào thiếu.
  **Verify:** script exit 0, không in dòng `MISSING` nào. Nếu có `MISSING` → manifest sai, quay lại 1.1. Không được sang task tiếp theo.
  *Đã pre-verify 2026-08-14 lúc propose: 26/26 path tồn tại, tổng 49 MB. Vẫn chạy lại lúc implement để bắt trường hợp folder nguồn thay đổi.*

- [x] **1.3 — Viết `sync.sh`**
  Script trong `$STG`: `rsync -a --files-from=manifest.txt "$SRC/" "$STG/"` rồi `cp "$STG/AI Agent Deck.dc.html" "$STG/index.html"`. Thêm `set -euo pipefail`.
  **Verify:** `bash -n "$STG/sync.sh"` (syntax check) exit 0.

- [x] **1.4 — Chạy `sync.sh` lần đầu**
  **Verify:** `find "$STG" -type f -not -path '*/.git/*' | wc -l` trả về `29` = 26 (manifest) + `index.html` + `sync.sh` + `manifest.txt`. Đối chiếu từng path manifest có mặt trong `$STG`. `du -sh "$STG"` ≈ 49 MB.

---

## Phase 2 — File riêng cho Pages

- [x] **2.1 — Xác nhận `index.html` giống hệt deck gốc**
  **Verify:** `diff "$STG/index.html" "$STG/AI Agent Deck.dc.html"` exit 0, không output.

- [x] **2.2 — Tạo `.nojekyll` rỗng ở gốc `$STG`** ⚠ **BẮT BUỘC — bỏ qua là deck hỏng trên live (R3)**
  **Verify:** `test -f "$STG/.nojekyll"` exit 0.

- [x] **2.3 — Tạo `.gitignore` chặn rác macOS**
  Nội dung: `.DS_Store`, `._*`, `.thumbnail`.
  **Verify:** `.image-slots.state.json` **KHÔNG** bị match — chạy `git check-ignore -v .image-slots.state.json` phải exit 1 (không ignore). File này là sidecar runtime, ignore nhầm là hỏng AC4.

- [x] **2.4 — Viết `README.md` cho repo**
  Ghi: đây là live view của Nexus Agent Deck, URL Pages, nguồn deck, cách update (`./sync.sh`), và lưu ý `.nojekyll` không được xoá.
  **Verify:** file tồn tại, có nhắc `.nojekyll`.

---

## Phase 3 — Verify local (chạy TRƯỚC khi commit — chặn lỗi vào git history vĩnh viễn)

- [x] **3.1 — Serve `$STG` qua HTTP**
  `python3 -m http.server 8765 --directory "$STG"` chạy background.
  **Verify:** `curl -sI http://localhost:8765/ | head -1` trả `200`.

- [x] **3.2 — Assert HTTP 200 cho toàn bộ asset quan trọng**
  Curl từng path: `/_ds/industry-20f39a08-3061-48e6-a859-56db016d2655/styles.css`, `/_ds/.../_ds_bundle.js`, `/deck-stage.js`, `/image-slot.js`, `/support.js`, `/.image-slots.state.json`, `/assets/nexus-avatar.png`, 4 file `/uploads/llm-wiki/*.dc.html`, `/uploads/llm-wiki/support.js`, `/uploads/llm-wiki/wiki-static.jsx`, 4 file `.mp4`, 2 file `.png` trong uploads.
  **Verify:** mọi path trả `200`. In bảng path → status. Bất kỳ `404` nào → manifest thiếu, quay lại 1.1.

- [x] **3.3 — Mở deck bằng browser tool, đọc console**
  Navigate `http://localhost:8765/`, chạy `read_console_messages` và `read_network_requests`.
  **Verify (AC2):** 0 request nào status 404. 0 lỗi console (trừ lỗi Google Fonts nếu offline — ghi chú riêng nếu gặp).

- [x] **3.4 — Verify style đã áp dụng (AC1)**
  Screenshot slide đầu.
  **Verify:** deck có style đúng, không phải HTML trần không CSS. So sánh với bản local mở bằng `file://`.

- [x] **3.5 — Verify image slot có ảnh (AC4)** ⚠ failure mode âm thầm
  Chuyển tới các slide có image slot, screenshot.
  **Verify:** các ô ảnh có nội dung, không trống. Nếu trống → `.image-slots.state.json` không load, kiểm tra lại 2.3 và 3.2.

- [x] **3.6 — Verify 4 iframe `llm-wiki` render (AC5)**
  Chuyển tới các slide chứa iframe, screenshot từng cái.
  **Verify:** cả 4 iframe hiện nội dung, không trắng.

- [x] **3.7 — Verify video + điều hướng slide (AC6, AC7)**
  Bấm play 1 video; thử phím mũi tên chuyển slide.
  **Verify:** video play được; slide chuyển được cả hai chiều.

- [x] **3.8 — Dừng HTTP server**
  **Verify:** `curl -sI http://localhost:8765/` fail (connection refused).

**🚦 GATE: Không sang Phase 4 nếu bất kỳ task 3.2–3.7 nào fail.** Sau khi commit thì blob nằm trong history vĩnh viễn.

---

## Phase 4 — Git & remote

- [x] **4.1 — `git init` + commit đầu tiên trong `$STG`**
  `git init -b main`, `git add -A`, commit.
  **Verify (chạy TRƯỚC khi push):** `git ls-files | wc -l` khớp số file mong đợi; `git ls-files | grep -c 'nojekyll'` = 1; `git ls-files | grep -c 'image-slots.state.json'` = 1; `git ls-files` **không** chứa file backup deck nào (`grep -i 'backup\|test-fix\|standalone'` = 0 kết quả).

- [x] **4.2 — Tạo repo public `mor-tungdv/nexus-agent-deck`**
  `gh repo create mor-tungdv/nexus-agent-deck --public --source="$STG" --remote=origin`
  **Nếu fail vì thiếu quyền tạo repo trong org `hardy-work` (R5):** dừng lại, báo user, hỏi chọn — (a) tạo dưới personal account `mor-tungdv`, hoặc (b) user tự tạo repo trên web UI rồi mình push. **Không tự ý đổi owner.**
  **Verify:** `gh repo view mor-tungdv/nexus-agent-deck --json visibility` trả `PUBLIC`.

- [x] **4.3 — Push lên `main`**
  Kiểm tra remote URL dùng đúng SSH host alias nếu cần (`github-mortungdv`).
  **Verify:** `git push -u origin main` exit 0; `gh repo view --json defaultBranchRef` trả `main`.

---

## Phase 5 — Bật Pages & verify live

- [x] **5.1 — Bật GitHub Pages, source `main` / root**
  `gh api repos/mor-tungdv/nexus-agent-deck/pages -X POST -f 'source[branch]=main' -f 'source[path]=/'`
  **Verify:** `gh api repos/mor-tungdv/nexus-agent-deck/pages --jq '.html_url'` trả URL, không phải 404.

- [x] **5.2 — Chờ Pages build xong**
  Poll `gh api repos/mor-tungdv/nexus-agent-deck/pages/builds/latest --jq '.status'`.
  **Verify (AC8):** status = `built`. Nếu `errored` → đọc `.error.message`, xử lý, không bỏ qua.

- [x] **5.3 — Assert `.nojekyll` hoạt động trên live (AC3)** ⚠ verify quan trọng nhất của phase này
  `curl -sI https://mor-tungdv.github.io/nexus-agent-deck/_ds/industry-20f39a08-3061-48e6-a859-56db016d2655/styles.css`
  **Verify:** HTTP `200`. Nếu `404` → `.nojekyll` không có tác dụng, deck sẽ mất style. Kiểm tra file có thực sự nằm trong commit không (`git ls-files .nojekyll`).

- [x] **5.4 — Verify toàn bộ AC trên URL live**
  Mở `https://mor-tungdv.github.io/nexus-agent-deck/` bằng browser tool. Chạy lại kiểm tra tương đương 3.3–3.7 nhưng trên live.
  **Verify:** AC1 ✓ AC2 ✓ AC4 ✓ AC5 ✓ AC6 ✓ AC7 ✓. Đặc biệt soi 404 do case-sensitivity (R/F4) — lỗi này chỉ xuất hiện trên live.

- [x] **5.5 — Báo cáo kết quả cho user**
  Đưa URL live, số file / dung lượng thực tế đã push, và bảng AC1–AC8 pass/fail. Nếu có AC nào fail → nói rõ, không claim hoàn thành.

---

## Rules check (R1–R6)

| Rule | Trạng thái |
|---|---|
| R1 — Mỗi task atomic, làm được trong 1 bước | ✓ 24 task, không task nào gộp nhiều mục đích |
| R2 — Mỗi task có bước verify chạy được | ✓ mọi task có dòng **Verify** với lệnh/assertion cụ thể |
| R3 — Verify-first ở chỗ có thể | ✓ 1.2 assert trước khi copy; Phase 3 verify trước khi commit; 4.1 verify trước khi push |
| R4 — Có gate rõ ràng giữa các phase | ✓ gate sau Phase 3 (trước khi vào git history) |
| R5 — Failure mode có đường xử lý, không "cứ chạy tiếp" | ✓ 1.2, 3.2, 4.2, 5.2, 5.3 đều nói rõ làm gì khi fail |
| R6 — Không claim hoàn thành khi chưa verify | ✓ 5.5 yêu cầu bảng AC pass/fail, cấm claim nếu có fail |
