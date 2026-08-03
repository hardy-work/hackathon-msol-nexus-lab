---
page: entity-person
name: "TùngDV"
assignee: tung-dv
project: nexus
task_count: { facts_ref: "raw/nexus-people.facts.json#tung-dv.task_count" }
estimate_h: { facts_ref: "raw/nexus-people.facts.json#tung-dv.estimate_h" }
actual_h: { facts_ref: "raw/nexus-people.facts.json#tung-dv.actual_h" }
raw_paths:
  - raw/nexus-config.md
  - raw/nexus-sprint1.md
  - raw/nexus-people.md
---

# TùngDV

Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.

## Ghi chú

Người này được khai trong Config nhưng rollup Sprint 1 ghi nhận **0 task**,
không có dòng task hoặc vai trò theo task trong nguồn raw. Số 0 vẫn chỉ dùng qua
`facts_ref`; không suy ra thêm tech-stack hay vai trò.

## Phạm vi

Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu
không được suy diễn thành “không có”.
