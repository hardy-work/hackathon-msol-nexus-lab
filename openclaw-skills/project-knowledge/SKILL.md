---
name: project-knowledge
description: Tra cứu thông tin dự án Nexus từ Excel/wiki/facts có provenance, citation và độ tin cậy rõ ràng. Dùng khi người dùng hỏi về task, assignee, role, sprint, effort, lịch, resource, risk, issue, backlog hoặc cần onboarding theo dữ liệu dự án; không dùng skill này để tự ý ghi Jira, gửi tin nhắn hay thay đổi dữ liệu.
---

# Project Knowledge

## Mục tiêu

Trả lời câu hỏi về dự án từ kho Nexus đã được kiểm chứng. Ưu tiên câu trả lời tất định từ DuckDB/facts; mọi số liệu phải truy được về nguồn. Không suy đoán khi kho thiếu dữ liệu.

## Cách gọi demo

Từ thư mục skill (`openclaw-skills/project-knowledge`):

```bash
python3 scripts/run.py \
  --project nexus \
  --query "ĐôNT đã bỏ ra bao nhiêu giờ trong Sprint 1?"
```

Wrapper mặc định chạy deterministic, không gọi mạng và không gọi LLM. Dùng `--llm` chỉ khi runtime Claude đã được cấu hình và cần câu hỏi mở; nếu không, giữ mặc định để bảo toàn tính tái lập.

Khi tích hợp Claude, đọc adapter tại `adapters/claude/CLAUDE.md`; adapter chỉ thay lớp runtime, không thay contract facts/citation.

## Hợp đồng trả lời

Skill trả JSON gồm:

- `status`: `in_kb`, `confident_no`, `not_in_kb` hoặc `error`;
- `answer`: câu trả lời tiếng Việt;
- `confidence`: `high`, `medium` hoặc `none`;
- `citations`: danh sách trang/ô nguồn;
- `reason`: giải thích ngắn về coverage, gate hoặc giới hạn dữ liệu;
- `tier`: bậc truy vấn đã trả lời;
- `project`: project đang tra cứu;
- `suggested_actions`: proposal read-only, luôn yêu cầu approval và mặc định rỗng.

Hiển thị citation cùng câu trả lời khi đưa lên giao diện chat. Giữ nguyên `not_in_kb` và `confident_no` như skill trả về, không đổi thành một loại “không có” chung.

## Quy tắc an toàn

1. Không tự tính hoặc làm tròn số nếu không có facts/source phù hợp.
2. `confident_no` chỉ hợp lệ khi dimension đóng và coverage đã ký.
3. Sheet đã nạp nhưng chưa ký coverage chỉ được trả `not_in_kb`, không được khẳng định phủ định.
4. Không thực hiện write action. Nếu người dùng muốn sửa Jira/Excel, trả lời context hiện có và chuyển yêu cầu cho action skill có permission/approval.
5. Khi `derived/facts.duckdb` chưa tồn tại, yêu cầu chạy `bash scripts/run_all.sh` rồi thử lại.
6. Nếu người dùng yêu cầu ghi/cập nhật, chỉ tạo `suggested_actions`; không thực hiện action.

## Demo flow

Chạy toàn bộ kịch bản:

```bash
bash demo/run_demo.sh
```

Kịch bản mẫu phải thể hiện đủ `in_kb`, `confident_no`, `not_in_kb` và câu trả lời số có citation. Bộ kiểm thử chuẩn nằm ở `questions.json` và chạy bằng `python3 scripts/eval.py`.
Bộ phủ theo sheet/cột nằm ở `questions_coverage.json` và chạy bằng
`python3 scripts/eval_coverage.py`; bộ này kiểm tra Resource plan, lịch, Summary,
task/status/priority, Config và các sheet rỗng. `scripts/response_style.py` được
gọi trong các eval để bắt output thiếu citation, lẫn runtime marker hoặc nhầm
`not_in_kb` thành phủ định chắc chắn.

Smoke test cho contract/paraphrase nằm ở `scripts/skill_selftest.py`.

Config chỉ khai báo vocabulary `tech_stack`; chưa có quan hệ người–tech-stack.
Vì vậy câu hỏi “ai làm JavaScript?” phải trả `not_in_kb`, không được suy ra từ
role hoặc từ danh mục công nghệ.

## Slack

Khi Agent được gọi từ Slack, dùng adapter tại `adapters/slack/`. Adapter nhận
Events API/slash-command JSON, giữ `channel_id`, `user_id`, `thread_ts`, format
Block Kit và không thực hiện write action. Chạy smoke test bằng:

```bash
python3 adapters/slack/slack_selftest.py
bash demo/run_slack_demo.sh
```

## Ranh giới tích hợp Agent

Agent PM có thể dùng output của skill để lập context, đề xuất action hoặc yêu cầu approval. Không đưa credential Jira/mail/meeting vào skill này. Các action tương lai nên nhận `citations` và `project` từ output để ghi audit log.
