---
name: new-hire-training
description: Tạo handbook onboarding cho nhân viên mới bằng cách tổng hợp tài liệu nội bộ và tài liệu dự án đã được kiểm chứng trong project-knowledge, kèm mục tiêu học tập, lộ trình, checklist, câu hỏi kiểm tra và citation. Dùng khi người dùng yêu cầu tạo tài liệu training/onboarding, kế hoạch 30-60-90 ngày, giáo trình nhập dự án hoặc tài liệu hướng dẫn cho dev/PM mới; không dùng để sửa KB, suy diễn chính sách hoặc thay thế tài liệu gốc.
---

# New-hire training

Tạo một tài liệu training có thể dùng ngay từ các trang wiki hiện tại. Mọi nội dung phải truy được về nguồn; nếu KB thiếu dữ liệu thì ghi rõ `Chưa có trong KB` thay vì tự điền thông tin.

## Quy trình

1. Xác định `project-knowledge` root. Ưu tiên `--kb-root`; nếu bỏ trống, dùng `../../project-knowledge` tính từ thư mục skill hoặc biến `PROJECT_KNOWLEDGE_ROOT`.
2. Chỉ đọc các trang wiki đã xuất bản (`wiki/sources`, `wiki/entities`, `wiki/concepts`, `wiki/case-studies`). Bỏ qua `index.md`, `log.md`, `.gitkeep`, file archive/snapshot và trang không có frontmatter hợp lệ.
3. Lọc theo visibility: cho phép `public` và `internal`; loại `restricted`, `confidential` hoặc giá trị không nhận diện. Không nới quyền theo tên người học.
4. Phân loại nguồn thành:
   - **Nội bộ công ty**: domain MOR/HR hoặc tên/raw path chứa `noi-quy`, `policy`, `handbook`, `hr`.
   - **Dự án**: `project: <project>` hoặc domain/tên/raw path chứa project đang chọn.
   - **Team**: `page: entity-person` thuộc project đang chọn.
5. Chạy generator:

   ```bash
   python scripts/create_training.py \
     --kb-root ../project-knowledge \
     --project nexus \
     --role developer \
     --roles-config config/role_profiles.yml \
     --name "Nhân viên mới" \
     --output ./generated/nexus-new-hire.md
   ```

6. Đọc lại output và kiểm tra: mỗi module có source reference, các con số giữ nguyên như nguồn, cảnh báo OCR được giữ nguyên, trạng thái freshness được hiển thị, và phần thiếu dữ liệu được ghi rõ. Không gọi Slack/Jira/Google Drive trong skill này.

## Profile theo vai trò

Generator nhận các role phổ biến `developer`, `qa`, `project-manager` và `hr-operations` (có alias như `backend-developer`, `tester`, `pm`, `hr`). Mỗi profile thêm module trọng tâm, hoạt động gợi ý và danh sách khoảng trống. Khoảng trống luôn được đánh dấu `[Chưa có trong KB]`, không được hiểu là một quy trình/policy đã tồn tại.

Với các trang entity chỉ có `raw_paths`, generator truy ngược `documents.yml` để hiển thị `doc_id/version` canonical và giữ lại `raw_paths` trong citation.

Artifact luôn gắn scope: `policy_fixed` cho Nội quy/chính sách cố định, `project_dynamic` cho resource/sprint/team/risk/workflow có thể thay đổi, và `role_guidance` cho hướng dẫn theo vai trò. Khi project thay đổi, kiểm tra/regenerate phần `project_dynamic`; không cần ingest lại nguồn `policy_fixed`.

Chạy evaluator offline sau khi sinh handbook:

```bash
python scripts/evaluate_training.py --dir ./generated
```

Khi chỉ có project/team thay đổi, dùng artifact handbook hiện tại để giữ nguyên
hai module `policy_fixed`:

```bash
python scripts/create_training.py \
  --kb-root ../project-knowledge --project nexus --role developer \
  --scope project_dynamic --previous ./generated/nexus-new-hire.md \
  --output ./generated/nexus-new-hire.project-refresh.md
```

## Hợp đồng đầu ra

Tài liệu Markdown phải có các phần sau, theo đúng thứ tự:

1. Hồ sơ người học và phạm vi tài liệu.
2. Mục tiêu sau khi hoàn thành.
3. Lộ trình module: nội bộ công ty, dự án, team/workflow, thực hành.
4. Checklist trước ngày đầu, tuần đầu và trước khi nhận task đầu tiên.
5. Câu hỏi kiểm tra kiến thức; câu nào không có dữ liệu phải gắn `[Chưa có trong KB]`.
6. Ma trận nguồn: file wiki, `doc_id`, version, visibility và ghi chú OCR nếu có.
7. Giới hạn và việc cần xác nhận với HR/PM.

Generator mặc định tạo nội dung deterministic, không cần LLM hay mạng. Có thể dùng LLM ở lớp ngoài để diễn đạt lại, nhưng không được bỏ citation, thêm số liệu hoặc biến đề xuất thành chính sách.

## Quy tắc nội dung

- Phân biệt **quy định bắt buộc**, **hướng dẫn dự án** và **đề xuất học tập** bằng nhãn rõ ràng.
- Không suy ra quyền lợi, deadline, vai trò, tech-stack hoặc quy trình khi nguồn không khai báo.
- Các trang OCR chỉ là bản nhận dạng; luôn giữ câu cảnh báo “đối chiếu bản gốc” và không gọi chúng là bản pháp lý cuối cùng.
- Với tài liệu nội bộ, chỉ đưa vào handbook khi trang có `visibility: internal` hoặc `public`; không copy raw/original bytes vào output.
- Khi nhiều nguồn mâu thuẫn, hiển thị cả hai citation và đánh dấu cần HR/PM xác nhận; không tự chọn một bên.
- Tài liệu sinh ra là artifact đầu ra, không được ghi vào `wiki/`, `raw/`, `structured/` hoặc `derived/` của project-knowledge.

## Tài nguyên

- `scripts/create_training.py`: generator deterministic cho handbook Markdown.
- `scripts/selftest.py`: kiểm tra lọc visibility, phân loại nguồn, citation và fail-closed behavior.
- `scripts/evaluate_training.py`: chấm cấu trúc, scope policy/project, citation, freshness và khoảng trống của artifact.
- `config/role_profiles.yml`: profile role có thể chỉnh mà không sửa generator.
- `references/training-contract.md`: schema module, quy tắc citation và checklist review.
