# Chỉ mục kho tri thức

Cập nhật ở Stage 4 (scripts/build_index.py). Trạng thái: **8 trang · 9 nguồn `raw/` · 1 tài liệu gốc**.

## Corpus (`domain`)

- **nexus** — corpus kế hoạch dự án Nexus (`nexus-plan.xlsx`).

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
| [[nexus-plan]] | `nexus-plan` | `nexus` | 9 |

## Khái niệm — `concepts/`

_(chưa có)_

## Phạm vi đã ký — `coverage.yml`

| quan hệ | phạm vi | tính đến |
|---|---|---|
| `person_role` | Config!H2:K15 | Nexus Plan (2026-08-03) |
| `person_task` | Sprint 1!A6:R65 | Nexus Plan (2026-08-03) |

Ngoài các dòng trên, hệ thống **không** được trả lời "chắc chắn không".
