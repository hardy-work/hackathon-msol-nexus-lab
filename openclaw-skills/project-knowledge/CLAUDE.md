# LLM-wiki — Hợp đồng nạp & trả lời (Nexus Plan)

Mọi bước ingest phải giữ provenance và không được bịa giá trị DIMENSION hoặc số đo.

## 0. Bốn tầng lưu trữ

| Tầng | Thư mục | Ai ghi |
|---|---|---|
| Bản gốc | `originals/` | người |
| Thô | `raw/` | script |
| Wiki | `wiki/` | LLM/script theo template |
| Dẫn xuất | `derived/` | script |

## 1. Ba loại trường

- DIMENSION: chọn từ enum đóng, không tự thêm.
- MEASURE: số phải là `facts_ref` hoặc `{facts, unit, src}`.
- open-vocabulary: chỉ dùng tìm kiếm, vắng mặt không có nghĩa là không tồn tại.

### 1.2 Hai chế độ khai MEASURE — và vì sao chúng được canh khác nhau

`facts_ref` (luồng SỐ) trỏ vào `raw/*.facts.json` do script sinh. LLM không gõ con số
nào, nên giá trị **không thể lệch by construction**.

`facts` chép (luồng VĂN) tồn tại vì tài liệu văn xuôi không có `.facts.json` — rút số
ra khỏi câu văn cần hiểu ngữ cảnh. Ở chế độ này **LLM gõ lại con số**, nên tính bất
biến trên mất, và phải bù bằng `numeric_guard` policy=declare (§4, Gate 3a):

- `src` phải có dạng `<đường dẫn raw> :: <mục>`, đường dẫn giải được trong corpus và
  thuộc bản current;
- mục phải tồn tại trong raw đó;
- giá trị phải có mặt **đúng trong mục ấy**, không phải đâu đó trong tài liệu;
- đơn vị nhận diện được cạnh số phải khớp `unit` đã khai;
- nguồn `ocr: true` thì cấm khai `facts` (LUẬT OCR) — kiểm từ frontmatter của raw do
  script ghi, không từ trường trang wiki do LLM ghi.

Thiếu cổng này, Gate 4 đi xác thực câu trả lời của LLM bằng chính lời khai trước đó của
LLM: gán `12` (thời hạn lưu log) cho `chu_ky_doi_mat_khau` vẫn lọt, vì 12 có thật ở chỗ
khác trong tài liệu.

## 2. Danh sách DIMENSION (Nexus Plan)

Nguồn gốc là `originals/nexus-plan.xlsx`, sheet `Config`.

### `role` — vai trò chuyên môn
```
BE · FE
```

### `assignee` — người phụ trách
| slug | nhãn gốc |
|---|---|
| `tung-dv` | `TùngDV` |
| `do-nt` | `ĐôNT` |
| `son-bh` | `SơnBH` |
| `kien-dt` | `KiênĐT` |
| `vinh-nv` | `VinhNV` |
| `long-vn` | `LongVN` |
| `hoang-mv` | `HoàngMV` |

### `task_status` — trạng thái công việc
```
Open · In progress · Done · Pending · Cancel
```

### `tech_stack` — danh mục công nghệ chuẩn (chưa phải mapping người–công nghệ)
```
HTML · CSS · JavaScript · React · Vue.js · C# · C++ · Python · ROR · Java · Node.js · Django · DevOps · Fullstack
```

### `project` — dự án
```
nexus
```

### `domain` — corpus
```
nexus · mor-software
```

## 3. Loại trang trong `wiki/`

| Loại | Thư mục | DIMENSION bắt buộc |
|---|---|---|
| `entity-person` | `wiki/entities/` | `assignee`, `project` (`role` tuỳ chọn) |
| `source` | `wiki/sources/` | `domain` (`project` tuỳ chọn) |
| `concept` | `wiki/concepts/` | — |
| `case-study` | `wiki/case-studies/` | `domain` (`project` tuỳ chọn) |

Mọi trang phải có `page`, `name`, `raw_paths`, `visibility`; source phải có thêm
`doc_id`, `version`. `visibility` chỉ nhận `public`, `internal`, `restricted`.

## 4. Sáu chặng & bốn cổng

```
INVENTORY → INTAKE → EXTRACT → STRUCTURE → WIKI-INGEST → REVIEW → PUBLISH
Gate 1 SHA256 · Gate 2 numeric ingest · Gate 3a lint + numeric declare · Gate 3b review
· Gate 4 numeric answer
```

Trang wiki của luồng VĂN có HAI phần, soi bằng HAI cổng khác nhau — thân bài văn xuôi
qua `check_transform` (tóm tắt được bỏ bớt, cấm bịa/làm tròn), frontmatter qua
`check_page_declarations` (§1.2). Đưa frontmatter YAML vào cổng văn xuôi là sai: cổng
đó đọc đơn vị bằng chữ đứng ngay sau con số, mà trong `facts: 8, unit: "ký tự"` thì
ngay sau `8` là dấu phẩy — một khai báo đúng bị báo là "số mới/đổi/làm tròn".

Định danh (số hiệu luật, ô Excel, mã task, `Sprint N`, `Điều N`) được che theo VỊ TRÍ
thật. Che theo khoảng cách sẽ để định danh nuốt số đo đứng cạnh nó — `Điều 7: 8 ký tự`
mất số 8 — và cửa sổ của cổng khai báo luôn bắt đầu bằng chính locator.

`check_transform` so hai pha. Pha 1 chỉ hỏi "có trị số nào chưa từng tồn tại không" —
đây là câu hỏi chống bịa và không bao giờ được nới. Pha 2 chỉ xét đơn vị của những trị
số còn nguyên ở cả hai vế: đổi đơn vị thật (`30 phút` → `30 giờ`) vẫn là lỗi cứng, còn
được/mất chú thích đơn vị là cảnh báo. So theo cặp `(trị số, đơn vị)` như bản trước thì
hai thao tác dàn lại hoàn toàn hợp lệ — đưa số vào ô bảng, và phục hồi dấu tiếng Việt
trên từ đơn vị — đều bị báo là "số mới", và số bịa thật lẫn vào giữa đống nhiễu đó.

### 4.1 Stage 3 KHÔNG sửa lỗi nguồn

Trên nguồn OCR, LLM có xu hướng sửa lỗi nó nhìn thấy: `385 ngày` → `365 ngày` theo Bộ
luật Lao động, `437.` → `43.7.` theo mạch đánh số. Prompt Stage 3 cấm việc này. Cổng số
không phân biệt được "sửa đúng nhờ kiến thức ngoài" với "bịa nghe hợp lý" — nếu nó cho
bản sửa đúng đi qua thì nó cũng sẽ cho số bịa đi qua. Lỗi nguồn phải nằm nguyên trong
`raw/` và `structured/`; nó không thành sự thật vì LUẬT OCR chặn khai `facts`, và nó
được sửa bằng bản gốc mới do người nạp lại, không bằng suy đoán của model.

`raw/` là provenance; truy vấn bảng dùng DuckDB, không đọc raw trực tiếp.

Gate 3a lint current pages và đồng thời quét page lịch sử đã supersede/retire. Mọi page
version cũ phải có `superseded_by` trỏ tới đúng page current cùng `doc_id`, version;
page generated bị loại khỏi nguồn có thể dùng `retired_by` trỏ tới page current của
document. Target, raw_paths lịch sử và link trong page lịch sử đều phải tồn tại. Page
lịch sử được miễn kiểm backlink current để không làm thay đổi ngữ nghĩa của snapshot cũ.

File upload phải đi qua `scripts/intake.py` trên staging/worktree. Intake lưu
`source_name` và `kind`, dùng SHA-256, identity tên/loại file và semantic digest
của workbook để phân biệt duplicate, no-op, initial ingest và re-ingest. File mới
được gán `doc_id` từ slug tên + UTC timestamp + hash collision-checked; tên file
không phải identity duy nhất. Heuristic khớp tên/loại chỉ trả `identity_review`,
không tự ghép vào document cũ; người duyệt phải xác nhận `--doc-id`. Re-ingest
không sửa `v1`: nó đăng ký original `@vN`, khai `supersedes`, archive trang 1:1
với `superseded_by`, rồi mới cho các gate downstream chạy.

Stage 5 sau Gate 3 phải chạy `scripts/build_rag_indexes.py`. Lệnh này tạo cả
`derived/bm25/` bằng `bm25s` và `derived/chroma/` bằng Chroma, rồi ghi
`derived/rag_indexes.json` với digest của input. Runtime chỉ phục vụ khi cả hai
index tồn tại và manifest còn khớp; thiếu index là lỗi triển khai, không phải lý do
để fallback im lặng. BGE-M3 là backend production mặc định; backend `hash` chỉ
dành cho CI/offline contract và vẫn phải tạo Chroma thật.

Query runtime bị khóa trong `scripts/filesystem_boundary.py`: chỉ đọc corpus và
index trong skill root, không nhận path tuyệt đối, `..` hoặc symlink thoát root.
DuckDB mở `read_only=True`; cache, conversation và telemetry là
operational state riêng ở `.runtime/` hoặc volume persistent, tuyệt đối không đặt
vào `originals/`, `raw/`, `wiki/` hay `derived/`. Production nên mount corpus ở chế
độ read-only của container/volume để có thêm enforcement ở OS.

Luồng VĂN có fixture riêng `scripts/van_selftest.py`: dựng `.docx`/`.pdf` thật, chạy
`extract_van` → cổng Stage 4 → Gate 3a → Gate 4, và khoá cả bốn luật ở §1.2 cùng LUẬT
OCR. Trước khi có nó, đây là lane duy nhất không có selftest và cũng là lane duy nhất
chưa từng chạy — hai cổng của nó mâu thuẫn nhau mà không ai biết.

CI bắt buộc chạy fixture `scripts/ingest_flow_selftest.py` theo chuỗi intake →
re-ingest v2 → Gate 3a → DuckDB/graph derive, cùng `scripts/lint_history_selftest.py`
và `scripts/review_selftest.py`. Luồng `ingest_flow.py --run` mặc định chạy live
Gate 3b bằng Claude; `--no-review` chỉ dành cho fixture/offline, không được dùng
để merge. Selftest CI kiểm tra chắc chắn logic đồng thuận K lượt không bị bỏ qua
khi chạy offline.

## 5. Quyền nói “CHẮC CHẮN KHÔNG”

Chỉ được nói khi quan hệ được lưu thành hàng dữ liệu, hai vế là DIMENSION đóng,
`coverage.yml` có receipt đầy đủ và runtime xác thực độc lập permission + approval id
của người ký. Sửa YAML trong repo không tự cấp authority. Thiếu điều kiện thì nói
“không tìm thấy”.

## 6. Điều cấm

- Không sửa `originals/` hoặc `raw/` bằng tay.
- Không gõ số đo trực tiếp vào wiki.
- Không tự thêm DIMENSION.
- Không commit `derived/`.
- Không thay canonical document tại chỗ; version mới phải khai `supersedes` và qua
  ingest worktree được người review. Lane Markdown đã hỗ trợ tài liệu `.md` có
  frontmatter: Stage 2 giữ nguyên body vào `raw/`, Stage 4 tạo trang `source`
  deterministic trong `wiki/sources/`; domain phải là giá trị đã curate trong
  `schema.yml` (hoặc được chuẩn hóa từ `org` đã curate).
