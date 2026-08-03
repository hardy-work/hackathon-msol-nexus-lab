---
page: entity-person
name: "ĐôNT"
assignee: do-nt
role: BE
project: nexus
task_count: { facts_ref: "raw/nexus-people.facts.json#do-nt.task_count" }
estimate_h: { facts_ref: "raw/nexus-people.facts.json#do-nt.estimate_h" }
actual_h: { facts_ref: "raw/nexus-people.facts.json#do-nt.actual_h" }
raw_paths:
  - raw/nexus-config.md
  - raw/nexus-sprint1.md
  - raw/nexus-people.md
---

# ĐôNT

Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.

## Ghi chú

Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở
nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.

## Phạm vi

Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu
không được suy diễn thành “không có”.
