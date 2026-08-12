# Handbook onboarding — Nhân viên mới

- **Dự án:** `nexus`
- **Vai trò:** `hr-operations`
- **Hồ sơ đào tạo:** `HR / Operations`
- **Snapshot KB:** `2026-08-10`
- **Freshness KB:** `fresh` — derived khớp với originals/raw/wiki hiện tại
- **Regeneration scope:** `all`
- **Policy scope:** `policy_fixed` — Nội quy/chính sách cố định, không refresh theo project.
- **Project scope:** `project_dynamic` — resource, sprint, team, risk và workflow có thể refresh khi project thay đổi.
- **Mục đích:** tài liệu học tập tổng hợp từ wiki đã xuất bản; không thay thế tài liệu gốc hoặc phê duyệt của HR/PM.

## 1. Mục tiêu sau khi hoàn thành

- Phân biệt quy định nội bộ, hướng dẫn dự án và đề xuất thực hành.
- Biết tìm nguồn, đọc `doc_id/version/visibility` và trích citation khi trả lời.
- Biết báo `Chưa có trong KB` thay vì suy đoán.
- Biết các điểm cần xác nhận với HR/PM trước khi thực hiện hành động có tác động.

## 2. Lộ trình training

### 2.1 Nội bộ công ty và phạm vi áp dụng

- **Kết quả cần đạt:** Biết tài liệu nào là quy định bắt buộc và khi nào cần hỏi HR.
- **Scope:** `policy_fixed`
- **Coverage:** `covered`
- **Hoạt động gợi ý:** Đánh dấu ba quy định người học cần xác nhận với HR trong ngày đầu.

**Nội dung có nguồn:**
- **Nội quy lao động** — Nguồn: `1760635210-MOR.BO.PRO.01_Nội quy lao động_v1.0.pdf` · cập nhật ngày 10/08/2026 · bởi MH_DoNT
  - **CHƯƠNG 1. NHỮNG QUY ĐỊNH CHUNG**
  - Điều 1. Định nghĩa
  - Điều 2. Các nguyên tắc áp dụng
  - **CHƯƠNG 2. HỢP ĐỒNG LAO ĐỘNG**
  - Điều 3. Các hình thức giao kết Hợp đồng lao động tại MOR

### 2.2 Thời gian, tác phong và an toàn

- **Kết quả cần đạt:** Biết các điểm cần tuân thủ tại nơi làm việc và các giới hạn của nguồn hiện có.
- **Scope:** `policy_fixed`
- **Coverage:** `not_in_kb`
- **Hoạt động gợi ý:** Viết lại một checklist trước khi bắt đầu ngày làm việc; không tự thêm giờ/điều kiện ngoài nguồn.

**Nội dung có nguồn:**
- `[Chưa có trong KB]` Không tìm thấy nguồn phù hợp.

### 2.3 Bối cảnh và mục tiêu dự án

- **Kết quả cần đạt:** Giải thích dự án đang quản lý những loại dữ liệu và hoạt động nào.
- **Scope:** `project_dynamic`
- **Coverage:** `covered`
- **Hoạt động gợi ý:** Mở trang nguồn dự án và chỉ ra nơi tra cứu resource, schedule, sprint, risk và issue.

**Nội dung có nguồn:**
- **Nexus Plan** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - `doc_id`: nexus-plan
  - `source_name`: Nexus Plan.xlsx
  - `raw_paths`: các bảng Nexus được trích từ `originals/nexus-plan.xlsx`.
  - Nguồn này là workbook kế hoạch dự án Nexus, gồm kế hoạch nguồn lực, tổng quan dự án, lịch tổng, backlog, sprint, rủi ro, issue và Config. Các bảng được giữ nguyên ở tầng `raw/` và tra cứu định lượng qua DuckDB; trang này chỉ là mục lục có cấu trúc.
  - [[tung-dv]] · [[do-nt]] · [[son-bh]] · [[kien-dt]] · [[vinh-nv]] · [[long-vn]] · [[hoang-mv]]

### 2.4 Team và cách nhận task

- **Kết quả cần đạt:** Biết thành viên/role nào đã được khai báo và cách kiểm chứng trước khi giao việc.
- **Scope:** `project_dynamic`
- **Coverage:** `covered`
- **Hoạt động gợi ý:** Chọn một task trong dữ liệu dự án và chuẩn bị câu hỏi làm rõ owner, status, nguồn và quyền thao tác.

**Nội dung có nguồn:**
- **ĐôNT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **HoàngMV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **KiênĐT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **LongVN** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **SơnBH** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **TùngDV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Người này được khai trong Config nhưng rollup Sprint 1 ghi nhận **0 task**, không có dòng task hoặc vai trò theo task trong nguồn raw. Số 0 vẫn chỉ dùng qua `facts_ref`; không suy ra thêm tech-stack hay vai trò.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **VinhNV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.

### 2.5 Trọng tâm HR/Operations và tuân thủ nội bộ

- **Kết quả cần đạt:** Nắm phạm vi Nội quy lao động, biết phần nào cần HR xác nhận và không nhầm dữ liệu dự án với chính sách HR.
- **Scope:** `role_guidance`
- **Coverage:** `partial`
- **Hoạt động gợi ý:** Đề xuất: lập checklist ngày đầu từ nguồn nội bộ và đánh dấu từng điểm cần HR xác nhận bản gốc.

**Nội dung có nguồn:**
- **Nội quy lao động** — Nguồn: `1760635210-MOR.BO.PRO.01_Nội quy lao động_v1.0.pdf` · cập nhật ngày 10/08/2026 · bởi MH_DoNT
  - **CHƯƠNG 1. NHỮNG QUY ĐỊNH CHUNG**
  - Điều 1. Định nghĩa
  - Điều 2. Các nguyên tắc áp dụng
  - **CHƯƠNG 2. HỢP ĐỒNG LAO ĐỘNG**
  - Điều 3. Các hình thức giao kết Hợp đồng lao động tại MOR

**Khoảng trống cần xác nhận:**

- `[Chưa có trong KB]` quy trình cấp tài khoản, hồ sơ, phúc lợi và payroll
- `[Chưa có trong KB]` đầu mối HR/Operations và SLA xử lý yêu cầu nhân sự
- `[Chưa có trong KB]` quy trình đào tạo bắt buộc, bảo mật và lưu hồ sơ

### 2.6 Thực hành tuần đầu

- **Kết quả cần đạt:** Hoàn thành một phiên hỏi đáp có citation và biết cách báo thiếu dữ liệu.
- **Scope:** `project_dynamic`
- **Coverage:** `covered`
- **Hoạt động gợi ý:** Đề xuất: chọn một quy định nội bộ, ghi citation và tách rõ điều bắt buộc với câu hỏi cần HR xác nhận.

**Nội dung có nguồn:**
- **Nexus Plan** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - `doc_id`: nexus-plan
  - `source_name`: Nexus Plan.xlsx
  - `raw_paths`: các bảng Nexus được trích từ `originals/nexus-plan.xlsx`.
  - Nguồn này là workbook kế hoạch dự án Nexus, gồm kế hoạch nguồn lực, tổng quan dự án, lịch tổng, backlog, sprint, rủi ro, issue và Config. Các bảng được giữ nguyên ở tầng `raw/` và tra cứu định lượng qua DuckDB; trang này chỉ là mục lục có cấu trúc.
  - [[tung-dv]] · [[do-nt]] · [[son-bh]] · [[kien-dt]] · [[vinh-nv]] · [[long-vn]] · [[hoang-mv]]
- **ĐôNT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **HoàngMV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **KiênĐT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **LongVN** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **SơnBH** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **TùngDV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Người này được khai trong Config nhưng rollup Sprint 1 ghi nhận **0 task**, không có dòng task hoặc vai trò theo task trong nguồn raw. Số 0 vẫn chỉ dùng qua `facts_ref`; không suy ra thêm tech-stack hay vai trò.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.
- **VinhNV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
  - Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.
  - Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
  - Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu không được suy diễn thành “không có”.

## 3. Checklist onboarding

### Trước ngày đầu

- [ ] Xác nhận vai trò, project và người hướng dẫn với PM/HR.
- [ ] Đọc các nguồn nội bộ trong ma trận nguồn; ghi lại điểm cần hỏi lại.
- [ ] Không coi thông tin thiếu trong KB là khẳng định không tồn tại.

### Tuần đầu

- [ ] Tra được trang overview của project và các entity team liên quan.
- [ ] Trả lời được câu hỏi onboarding kèm citation.
- [ ] Thử một quy trình read-only; chưa tự ghi Jira/Sheet/Slack.

### Trước task đầu tiên

- [ ] Xác nhận acceptance criteria, owner, status và nguồn dữ liệu.
- [ ] Xác nhận quyền thao tác; mọi write action phải qua approval của skill tương ứng.
- [ ] Biết nơi báo blocker, risk hoặc thông tin mâu thuẫn.

## 4. Câu hỏi kiểm tra

1. Nguồn nào là quy định nội bộ và phải đối chiếu bản gốc trước khi áp dụng?
2. Project overview nằm ở đâu và nó dẫn tới những loại dữ liệu nào?
3. Khi không tìm thấy thông tin về tech-stack/owner, cần trả lời thế nào? — **`Chưa có trong KB`**, không suy diễn.
4. Citation tối thiểu cần có những trường nào? — tên file nguồn, ngày cập nhật và người cập nhật.
5. Ai có quyền phê duyệt thay đổi dữ liệu dự án? — `[Chưa có trong KB]` nếu nguồn hiện tại chưa khai báo.
6. Quy trình hồ sơ, tài khoản, phúc lợi/payroll và đầu mối HR? — `[Chưa có trong KB]`
7. Đào tạo bắt buộc và quy trình lưu hồ sơ nhân sự? — `[Chưa có trong KB]`

## 5. Ma trận nguồn

- **ĐôNT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **HoàngMV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **KiênĐT** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **LongVN** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **SơnBH** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **TùngDV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **VinhNV** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **Nexus Plan** — Nguồn: `Nexus Plan.xlsx` · cập nhật ngày 03/08/2026 · bởi NexusBot (hệ thống)
- **Nội quy lao động** — Nguồn: `1760635210-MOR.BO.PRO.01_Nội quy lao động_v1.0.pdf` · cập nhật ngày 10/08/2026 · bởi MH_DoNT

## 6. Giới hạn cần xác nhận

- Freshness hiện tại: `fresh` — derived khớp với originals/raw/wiki hiện tại
- Nếu freshness là `stale` hoặc `unknown`, rebuild/kiểm tra `knowledge-base` trước khi dùng handbook cho quyết định mới.
- Tài liệu chỉ phản ánh snapshot KB tại thời điểm sinh; kiểm tra freshness trước khi dùng cho quyết định mới.
- Thông tin không xuất hiện trong ma trận nguồn không được coi là không tồn tại.
- HR/PM phải xác nhận nội dung thiếu hoặc mâu thuẫn trước khi phát hành handbook chính thức.
