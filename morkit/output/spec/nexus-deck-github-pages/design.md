# Design — Live view cho Nexus Agent Deck trên GitHub Pages

**Change:** `nexus-deck-github-pages`
**Created:** 2026-08-14

---

## 1. Tech stack

Đây là change deploy static site — **không có dependency ngôn ngữ / package manager nào**. Không có `package.json`, không có build step, không có framework. Vì vậy không có library nào cần verify qua Context7; toàn bộ stack là CLI tool sẵn có trên máy.

| Tool | Version (verified 2026-08-14) | Dùng để |
|---|---|---|
| `git` | 2.39.3 (Apple Git-146) | init / commit / push |
| `gh` | 2.97.0 | tạo repo, bật Pages qua REST API |
| `rsync` | openrsync protocol 29 (macOS built-in) | copy staging theo manifest |
| `python3` | 3.14.6 | `http.server` để verify local |
| `curl` | macOS built-in | assert HTTP status trong verify |

**Runtime của deck (không cần cài, đã nằm trong file):** `deck-stage.js`, `image-slot.js`, `support.js`, `_ds` design-system bundle. Deck load Google Fonts từ CDN (`fonts.googleapis.com`) — external dependency duy nhất, hoạt động bình thường trên Pages qua HTTPS.

**Auth:** `gh` đang login account `mor-tungdv`, scopes `gist, read:org, repo`. Git protocol: SSH, qua host alias `github-mortungdv`.

---

## 2. Kiến trúc

```
SOURCE (read-only, không sửa)         STAGING                      REMOTE
~/Downloads/Nexus Agent/       →   ~/Desktop/nexus-agent-deck/  →  mor-tungdv/
  119 files, 81 MB                    30 files, 49 MB               nexus-agent-deck
                                                                    (public, main)
        │                                    │                            │
        │  rsync --files-from                │  git push                  │
        │  (slim manifest)                   │                            ▼
        │                                    │                    GitHub Pages
        └─ + .nojekyll        (NEW)          │                    source: main / root
           + index.html       (copy)         │                            │
                                             │                            ▼
                                    python3 -m http.server    mor-tungdv.github.io/
                                    → verify AC1-AC7          nexus-agent-deck/
                                      TRƯỚC khi commit           → verify AC1-AC8
```

**Nguyên tắc:** folder nguồn `~/Downloads/Nexus Agent` là **read-only** trong suốt change này. Mọi thao tác diễn ra trên staging folder. Lý do: folder nguồn là bản làm việc của deck, không được để deploy làm hỏng.

---

## 3. Các quyết định thiết kế

### D1 — Staging folder tách rời, không `git init` trực tiếp trong folder nguồn

Nếu `git init` ngay trong `~/Downloads/Nexus Agent` thì phải dùng `.gitignore` để loại 82 file thừa. Cách đó dễ sai (dễ sót, dễ vô tình commit), và biến folder làm việc thành repo — thay đổi ngữ nghĩa của nó.

Staging folder riêng cho phép **allow-list** thay vì **deny-list**: chỉ copy đúng thứ có trong manifest. File nào không có trong manifest thì về mặt vật lý không tồn tại để mà commit nhầm.

Vị trí staging: `~/Desktop/nexus-agent-deck` (cạnh repo code, dễ tìm, không phải `/tmp` vì sẽ dùng lại khi update deck sau này).

### D2 — `index.html` là bản copy, không phải symlink hay redirect

Git không theo symlink theo cách Pages cần, và redirect stub tạo URL có `%20`. Copy là cách đơn giản và đúng nhất.

Hệ quả: có 2 file nội dung giống hệt trong repo (`index.html` + `AI Agent Deck.dc.html`), tốn thêm 68 KB — không đáng kể. Bước copy được đưa vào script sync (D5) nên không quên được.

Giữ lại cả file gốc `AI Agent Deck.dc.html` để tên file trên repo khớp với bản local, dễ đối chiếu.

### D3 — `.nojekyll` là bắt buộc, verify bằng assert HTTP

Không có `.nojekyll`, Jekyll bỏ qua `_ds/` → deck mất style và runtime. Đây là failure mode dễ bị bỏ sót nhất vì trang **vẫn load**, chỉ là xấu và không chạy.

Vì vậy AC3 không verify bằng mắt mà bằng `curl -sI` assert status 200 trên chính `_ds/styles.css`.

### D4 — Verify local trước, verify live sau (hai vòng, không bỏ vòng nào)

Verify local bắt được: thiếu file trong manifest, đường dẫn tương đối sai, sidecar không load.
Verify live bắt được: Jekyll ăn `_ds/`, case-sensitivity, MIME type mà local server đoán khác Pages.

Hai vòng bắt hai lớp lỗi khác nhau — không thay thế được cho nhau. Verify local đặc biệt quan trọng vì nó chạy **trước** khi blob vào git history.

### D5 — Script sync `sync.sh` nằm trong staging repo

Thay vì copy tay, viết `sync.sh` đọc manifest và rsync từ nguồn sang staging + regenerate `index.html`. Commit script này vào repo.

Giải quyết Open Question Q2 (quy trình update về sau): lần sau sửa deck chỉ cần chạy `./sync.sh && git commit -am "update deck" && git push`.

### D6 — Verify từng bước bằng assertion, không bằng "nhìn thấy có vẻ ổn"

Mỗi task trong `tasks.md` có bước verify chạy được, exit code khác 0 khi fail. Đặc biệt: task đối chiếu **danh sách file thực tế trong staging** với manifest — đếm file, so khớp tên — trước khi commit.

---

## 4. Failure modes đã lường & cách chặn

| Failure mode | Triệu chứng | Chặn ở đâu |
|---|---|---|
| Jekyll ăn `_ds/` | Trang load nhưng không style, không chạy được | `.nojekyll` (task 2.2) + AC3 assert curl |
| Thiếu `deck-stage.js` | Slide không render (`<x-import>` fail) | Manifest + verify local console |
| Thiếu `.image-slots.state.json` | **Image slot trống, không lỗi nào báo ra** | Manifest + AC4 quan sát trực quan |
| Thiếu `uploads/llm-wiki/support.js` hoặc `wiki-static.jsx` | 4 iframe trắng hoặc lỗi | Manifest + AC5 |
| Case-sensitivity (macOS vs Pages) | Ảnh/video 404 chỉ trên live, local ổn | AC2 trên **live** (không phải local) |
| Tạo repo trong org fail (thiếu quyền) | `gh repo create` báo lỗi | Fallback task 4.2 |
| Pages build fail / chưa propagate | 404 tại URL | Task 5.2 poll build status |

---

## 5. Rollback

Change này không sửa gì trong folder nguồn và không sửa gì trong repo code hiện tại. Rollback = xoá repo `mor-tungdv/nexus-agent-deck` và xoá staging folder. Không có tác dụng phụ nào cần undo.

Lưu ý: rollback **không** thu hồi được nội dung đã public. Sau khi push, phải coi như video và tài liệu trong deck đã phát tán (R1 — user đã confirm chấp nhận).
