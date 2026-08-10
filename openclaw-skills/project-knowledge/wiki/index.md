# Chỉ mục kho tri thức

Cập nhật ở Stage 4 (scripts/build_index.py). Trạng thái: **9 trang · 11 nguồn `raw/` · 3 tài liệu gốc**.

## Corpus (`domain`)

- **nexus** — corpus kế hoạch dự án Nexus (`nexus-plan.xlsx`).
- **mor-software** — hồ sơ nguồn MOR Software được nạp từ Markdown.

## Con người — `entities/`

| Trang | assignee | role | task (Sprint 1) |
|---|---|---|---|
| [[do-nt]] | `do-nt` | `BE` | 10 |
| [[hoang-mv]] | `hoang-mv` | `FE` | 10 |
| [[kien-dt]] | `kien-dt` | `FE` | 10 |
| [[long-vn]] | `long-vn` | `BE` | 10 |
| [[son-bh]] | `son-bh` | `BE` | 10 |
| [[vinh-nv]] | `vinh-nv` | `FE` | 10 |
| [[tung-dv]] | `tung-dv` | _n/a_ | 0 |

> Cột task ở đây là **bản sao để đọc nhanh**, không phải nguồn sự thật.
> Nguồn sự thật là `facts_ref` trong frontmatter từng trang.

## Nguồn — `sources/`

| Trang | doc_id | domain | nguồn `raw/` |
|---|---|---|---|
| [[noi-quy-lao-dong-20260808T041339Z-aa1429cc79]] | `noi-quy-lao-dong-20260808T041339Z-aa1429cc79` | `mor-software` | 1 |
| [[nexus-plan]] | `nexus-plan` | `nexus` | 9 |

## Khái niệm — `concepts/`

_(chưa có)_

## Phạm vi có approval receipt — `coverage.yml`

| quan hệ | phạm vi | tính đến | approval |
|---|---|---|---|
| `person_role` | Config!H2:K15 | Nexus Plan (2026-08-03) | `nexus-demo-person-role-20260803` |
| `person_task` | Sprint 1!A6:R65 | Nexus Plan (2026-08-03) | `nexus-demo-person-task-20260803` |

Receipt chỉ có hiệu lực khi runtime xác thực người ký, permission và approval id. Ngoài phạm vi đã xác thực, hệ thống **không** được trả lời "chắc chắn không".
