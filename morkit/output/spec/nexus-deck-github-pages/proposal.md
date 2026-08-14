# Proposal — Live view cho Nexus Agent Deck trên GitHub Pages

**Change:** `nexus-deck-github-pages`
**Created:** 2026-08-14
**Status:** Proposed
**Design log:** [2026-08-14-nexus-deck-github-pages-design.md](../../design-logs/2026-08-14-nexus-deck-github-pages-design.md)

---

## 1. What

Publish deck trình bày Nexus Agent (`~/Downloads/Nexus Agent`, index là `AI Agent Deck.dc.html`) thành một live view public trên GitHub Pages, host tại repo riêng `mor-tungdv/nexus-agent-deck`.

URL kết quả dự kiến: `https://mor-tungdv.github.io/nexus-agent-deck/`

Phạm vi: publish **bản slim** — 26 file / 49 MB copy từ nguồn, là closure phụ thuộc đã verify của deck, thay vì nguyên folder 119 file / 81 MB. Cộng thêm 6 file sinh mới (`index.html`, `.nojekyll`, `sync.sh`, `manifest.txt`, `README.md`, `.gitignore`) → **32 file trong repo**.

## 2. Why

Hiện tại deck chỉ tồn tại dưới dạng folder local. Muốn chia sẻ phải gửi nguyên 81 MB file, và người nhận phải mở đúng file trong đúng cấu trúc thư mục — vì deck **không self-contained**. Một URL giải quyết cả hai vấn đề.

## 3. Scope

### In scope

- Dựng staging folder theo slim manifest (mục 5).
- Thêm `.nojekyll` và `index.html` (copy của deck gốc).
- Verify local qua HTTP server trước khi commit.
- `git init`, commit, tạo repo `mor-tungdv/nexus-agent-deck` (public), push.
- Bật GitHub Pages (source: `main` / root).
- Verify trên URL live.

### Out of scope

- Sửa nội dung deck (slide, text, layout).
- Nén / tối ưu video hoặc ảnh.
- Inline Google Fonts để chạy offline (ghi nhận ở Open Question Q3 trong design log).
- Custom domain.
- CI/CD tự động sync deck khi bản local thay đổi (Q2 — quy trình update về sau).

## 4. Rủi ro & quyết định đã chốt

| ID | Nội dung | Quyết định |
|---|---|---|
| R1 | **Repo phải public.** Pages trên private repo cần gói trả phí. Toàn bộ nội dung deck (video meeting notes, kiến trúc multi-tenant, use case PM Agent) sẽ public với bất kỳ ai có URL. | **User đã confirm: OK public** (2026-08-14) |
| R2 | 43 MB video vào git history vĩnh viễn, không gỡ được nếu không rewrite history | Chấp nhận — commit nguyên bản, ưu tiên chất lượng demo |
| R3 | Jekyll của Pages bỏ qua folder `_`-prefix → mất `_ds/` | Bắt buộc có `.nojekyll` (task 2.2) |
| R4 | Thiếu file trong closure → deck hỏng âm thầm (không báo lỗi) | Verify local bắt buộc trước khi push (phase 3) |
| R5 | `gh` đang auth bằng account `mor-tungdv`, scope `gist, read:org, repo`. Tạo repo dưới org `hardy-work` có thể fail nếu thiếu quyền create trong org. | **Đã xảy ra** — xem Deviation D-1 |

## 4b. Deviation trong lúc implement

### D-1 — Owner đổi từ `hardy-work` sang `mor-tungdv`

R5 xảy ra, nhưng nguyên nhân sâu hơn dự đoán ban đầu:

`gh repo create hardy-work/nexus-agent-deck` fail với `mor-tungdv cannot create a repository for hardy-work`. Chẩn đoán cho thấy **`hardy-work` là một User account, không phải Organization** (`gh api users/hardy-work → "type": "User"`). Không ai ngoài chính chủ tạo được repo dưới một user account — đây không phải vấn đề scope hay quyền org.

Thêm nữa, trên repo `hardy-work/hackathon-msol-nexus-lab`, `mor-tungdv` có `push: true` nhưng **`admin: false`** → kể cả phương án `gh-pages` branch trên repo sẵn có cũng không bật được Pages, vì bật Pages cần quyền admin.

Theo fallback ở task 4.2, đã dừng và hỏi user. **User chọn: tạo dưới `mor-tungdv`.**

Hệ quả: URL thành `https://mor-tungdv.github.io/nexus-agent-deck/`. Muốn về `hardy-work` sau này thì dùng GitHub **Transfer ownership** (giữ nguyên history, tự redirect URL cũ).

### D-2 — Remote phải dùng SSH host alias

`git push` đầu tiên fail: `Permission to mor-tungdv/nexus-agent-deck.git denied to dflmanh`. SSH mặc định tới `github.com` trên máy này resolve sang identity khác. Máy có alias `github-mortungdv` trong `~/.ssh/config` trỏ đúng key `id_rsa_github_mortungdv`.

Remote đã đổi thành `git@github-mortungdv:mor-tungdv/nexus-agent-deck.git`. **Lưu ý cho lần clone/push sau:** dùng alias này, không dùng `git@github.com:`.

## 5. Slim manifest — 26 file copy, 49 MB

Nguồn: `/Users/tungdao/Downloads/Nexus Agent` (đã verify 2026-08-14: cả 26 path đều tồn tại, tổng đúng 49 MB)

```
/
  index.html                    ← copy của AI Agent Deck.dc.html
  AI Agent Deck.dc.html            68K
  .nojekyll                        NEW — bắt buộc (R3)
  deck-stage.js                   135K
  image-slot.js                    64K
  support.js                       68K
  .image-slots.state.json         267K   ← sidecar runtime
  h3kp6lpjoe5t2jhcslxsowx9lxk8adk9jiraengo-msrokfp3-4s1q.png   944K
  mot-pm-chuyen-nghiep-can-thuc-hien-lap-k-msrneunb-9f41.jpg    48K
  product-manager-msro590o-gz9u.webp                            72K
  _ds/industry-20f39a08-3061-48e6-a859-56db016d2655/            36K
      (_ds_bundle.js, styles.css, _ds_manifest.json,
       _adherence.oxlintrc.json, readme.md)

/assets
  nexus-avatar.png                                             1.1M

/uploads
  agent-orchestration.png                                      1.4M
  multi-tenant.png                                             1.7M
  summary-evidence.mp4                                          18M
  meeting-notes-a958a123.mp4                                    16M
  daily-repor-risk-assessment.mp4                              5.4M
  reminder-update-log-task-8dbe70f2.mp4                        3.7M

/uploads/llm-wiki
  kien-truc-tong-the.dc.html                                    12K
  nap-tri-thuc.dc.html                                         4.0K
  to-chuc-tri-thuc.dc.html                                      28K
  truy-xuat-du-lieu.dc.html                                     24K
  support.js                                                    68K
  wiki-static.jsx
```

### Loại bỏ (93 file, ~32 MB)

7 backup deck · `animations-v3.jsx` · `scene-chuan-hoa.jsx` · `tweaks-panel.jsx` · `project-manager-pm-1-msro2u8t-qbvu.jpeg` · `export/` · `screenshots/` · `.DS_Store` · `.thumbnail` · ~30 file không được reference trong `uploads/` · phần còn lại của `uploads/llm-wiki/`.

## 6. Acceptance criteria

| # | Tiêu chí | Cách verify |
|---|---|---|
| AC1 | Deck load tại URL live, style đúng (không phải HTML trần) | Mở URL, so sánh với bản local |
| AC2 | Console **0 lỗi 404** | DevTools Console + Network tab |
| AC3 | `_ds/styles.css` và `_ds/_ds_bundle.js` trả HTTP 200 | `curl -sI` — chứng minh `.nojekyll` hoạt động (R3) |
| AC4 | `.image-slots.state.json` trả 200 và các image slot có ảnh | Quan sát trực quan các slide có ảnh |
| AC5 | 4 iframe `uploads/llm-wiki/*.dc.html` render đúng, không trắng | Chuyển tới các slide chứa iframe |
| AC6 | 4 video mp4 play được | Bấm play từng video |
| AC7 | Điều hướng slide (next/prev) hoạt động | Thử phím mũi tên / click |
| AC8 | Repo `mor-tungdv/nexus-agent-deck` public, Pages build success | `gh api repos/mor-tungdv/nexus-agent-deck/pages` |
