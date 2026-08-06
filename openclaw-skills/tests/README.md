# tests/ — test offline cho phần logic dễ sai âm thầm

```bash
bash openclaw-skills/tests/run.sh
```

Không cần mạng, không cần API key, không đụng sheet thật, chạy hết trong ~2 giây.

## Vì sao chỉ test mấy chỗ này

Phần lớn hai skill là **luật cho bot đọc** (`SKILL.md`, `*-rules.md`) — không
test tự động được. Nhưng có hai đoạn là code Python thuần, và cả hai đều thuộc
loại **sai mà không báo lỗi**:

| File | Logic | Sai thì sao |
| --- | --- | --- |
| [`test_sheet_columns.py`](test_sheet_columns.py) | `headers_of` / `resolve_columns` của [`sheet-task.sh`](../gg-sheet/scripts/sheet-task.sh) | Tab Sprint có **2 cột tên `Start Date`** và **2 cột chứa chữ `Estimate`** (khối `PLAN` và khối `Actual`). Khớp nhầm là **ghi đè giờ plan của PM** — hỏng dữ liệu gốc, không exit code nào nổ |
| [`test_resource_plan.py`](test_resource_plan.py) | dò cột ngày + chia nhóm thiếu giờ của [`resource-plan-members.sh`](../reminder-followup/scripts/resource-plan-members.sh) | Dò trượt cột ngày thì script vẫn `exit 0`, vẫn in danh sách — chỉ là nhắc nhầm người đang nghỉ hoặc bỏ sót người đi làm. Không ai biết cho tới khi có người kêu |

Đây đúng là loại lỗi mà review bằng mắt hay bỏ qua: không crash, không log đỏ,
chỉ là kết quả sai.

## Cách test chạy được offline

- `MOCK_SHEET_RESPONSE_FILE` — bơm sẵn payload của Sheets API cho
  `resource-plan-members.sh` thay cho `curl`. **Cron không bao giờ set biến này**;
  nó chỉ đọc file, không đổi hành vi nào khác.
- `LOGTIME_TODAY=YYYY-MM-DD` — ghim "hôm nay" để test được thứ Bảy, ngày chưa có
  cột, tháng khác… mà không phải đợi tới ngày đó.
- `OPENCLAW_STATE_DIR` trỏ vào chỗ không tồn tại — không lấy được bot token nên
  script bỏ qua bước đối chiếu `users.info` (bước duy nhất cần mạng).
- `EFFORT_LEDGER_FILE` — trỏ sổ cái effort vào thư mục tạm.
- Với `sheet-task.sh` thì python nằm trong heredoc của bash nên không `import`
  được: test đọc file, cắt lấy đoạn từ dòng `import` tới ngay trước khối
  `if CMD == "find"` (toàn `def`, không gọi mạng) rồi `exec`.

## Case đang được giữ

Ngoài phần khớp cột, các case đáng chú ý:

- **Xong sớm hơn plan không bao giờ bị coi là thiếu giờ** — est 8h làm 3h rồi
  nhảy task khác 5h là `3 + 5 = 8` → đủ công, im lặng. Đây là lý do phải cộng
  **tổng cả ngày** chứ không xét từng task.
- **Nghỉ nửa buổi** — ô công ghi `4` thì mốc so tự thành 4, không cần luật riêng.
- **`hoàn thành 90%` không phải Done**, còn `đã hoàn thành` / `done ✅` thì có —
  cùng bộ chữ với [`log-task-rules.md`](../reminder-followup/template/log-task-rules.md).
- **Delta âm** (dev khai lại thấp hơn lần trước) phải làm tổng ngày **giảm**.
- Sổ cái chưa tồn tại / hỏng → không crash, không chặn việc log.
