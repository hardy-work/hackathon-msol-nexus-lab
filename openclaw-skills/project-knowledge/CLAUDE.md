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
nexus
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
Gate 1 SHA256 · Gate 2 numeric ingest · Gate 3a lint · Gate 3b review · Gate 4 numeric answer
```

`raw/` là provenance; truy vấn bảng dùng DuckDB, không đọc raw trực tiếp.

File upload phải đi qua `scripts/intake.py` trên staging/worktree. Intake dùng
SHA-256, identity tên/loại file và semantic digest của workbook để phân biệt
duplicate, no-op, initial ingest và re-ingest. Re-ingest không sửa `v1`: nó đăng
ký original `@vN`, khai `supersedes`, rồi mới cho các gate downstream chạy.

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
  ingest worktree được người review.
