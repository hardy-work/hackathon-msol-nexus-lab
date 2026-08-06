# Slack-triggered ingest

NexusBot owns Slack transport. Khi người dùng mention bot kèm file, NexusBot
truyền Slack user ID tin cậy vào `scripts/ingest_proposal.py`. Không dùng role
hoặc nội dung text tự do để cấp quyền; allowlist trong `access.yml` là nguồn
quyết định duy nhất.

## Quyền ingest

Hiện có 10 Slack user được phép nạp:

| Slack user ID | Tên |
|---|---|
| `U03H0QB426A` | MH_TungDV |
| `U03Q60UCBJS` | MA_Toan |
| `U03SC6QAP52` | MH_PhongDT |
| `U03TJ5FG3K7` | MH_Duong_MH |
| `U08FT511ZEF` | MH_HoangMV |
| `U08GQJRUT3Q` | MH_KienDT |
| `U09PXK5SCP4` | MH_Ngoc Long |
| `U09QRTUHX24` | MH_SonBH |
| `U0A2PDFHHL7` | MH_VinhNV |
| `U0APQSSGKTM` | MH_DoNT |

Không có bước approve/reject. User nằm trong allowlist sẽ được chạy thẳng qua
intake và ingest; user khác bị `forbidden` ngay lúc tạo proposal.

## Tạo proposal

```bash
python3 scripts/ingest_proposal.py create \
  --file /staging/upload.xlsx \
  --actor U0APQSSGKTM \
  --name MH_DoNT \
  --channel-id C123 \
  --thread-ts 1785313275.818529 \
  --message-ts 1785313276.100000
```

Lệnh kiểm tra file tồn tại, loại file, kích thước, symlink, SHA-256 và quyết
định identity/version của `intake.py`. Proposal được lưu ngoài corpus tại
`PROJECT_KNOWLEDGE_STATE_DIR/ingest-proposals/`.

Nếu tên file khớp document cũ nhưng chưa đủ căn cứ chọn identity, proposal dừng
ở `awaiting_identity`. Một user trong allowlist phải xác nhận `doc_id`:

```bash
python3 scripts/ingest_proposal.py confirm-identity <proposal_id> \
  --doc-id nexus-plan --actor U0APQSSGKTM
```

Sau khi xác nhận, proposal chuyển thành `ready_to_ingest`; không cần approve.

## Review artifact

```bash
python3 scripts/ingest_proposal.py review <proposal_id>
```

Artifact deterministic gồm `review-artifact.json` và Markdown. Với Excel, mọi
cell không rỗng được giữ cùng sheet, address, giá trị hiển thị, công thức,
number format và source locator. NexusBot có thể dùng JSON này để tạo Google
Sheet/Doc và gửi link thông báo; Google credential nằm ở adapter ngoài skill.

Review artifact là bản kiểm tra/audit, không phải source of truth. File upload,
raw artifact và wiki generated mới là provenance của corpus.

## Chạy ingest và publish

```bash
python3 scripts/ingest_runner.py run <proposal_id>
```

Trong Gateway deploy, NexusBot phải gọi bản runner từ Git repository chính,
không gọi bản copy trong workspace runtime. Có thể đặt hai biến môi trường sau
cho host runner:

```bash
export PROJECT_KNOWLEDGE_REPO=/Users/mor_minhhieu/repos/hackathon-msol-nexus-lab
export PROJECT_KNOWLEDGE_CLAUDE_BIN=/opt/homebrew/bin/claude
export PROJECT_KNOWLEDGE_PYTHON=/Users/mor_minhhieu/.openclaw/workspace-hackathon/skills/project-knowledge/.venv/bin/python
$PROJECT_KNOWLEDGE_PYTHON /Users/mor_minhhieu/repos/hackathon-msol-nexus-lab/openclaw-skills/project-knowledge/scripts/ingest_runner.py run <proposal_id>
```

`PROJECT_KNOWLEDGE_STATE_DIR` vẫn trỏ tới state directory dùng chung của
Gateway; repo chính chỉ là nơi lấy code và tạo isolated worktree. `run_all.sh`
kiểm tra `openpyxl` trước khi chọn Python để tránh rơi về system Python thiếu
dependency. Runner tự động dừng ở `ready_to_publish`, không tự merge vào corpus
chính.

Runner tự tạo review artifact local nếu NexusBot chưa tạo trước, sau đó tạo
isolated worktree, register source, chạy extractor, lint, Gate 3b, DB/graph/RAG
derive và `run_all.sh`. Runner dừng ở `ready_to_publish` để deployment layer
publish atomically, gọi `runtime_engine.KnowledgeRuntime.reload()`, rồi ghi nhận:

Với initial ingest, Gate 3b chỉ review các trang `wiki/*.md` vừa được tạo hoặc
thay đổi trong isolated worktree; không review lại toàn bộ corpus. Điều này giữ
được kiểm tra nội dung cho write-set mới và tránh đưa các trang source lớn,
không liên quan, vào một prompt review. Re-ingest vẫn review đúng write-set do
`reingest-plan.json` khai báo.

```bash
python3 scripts/ingest_runner.py record-published <proposal_id> \
  --corpus-version nexus-... --runtime-reloaded
```
