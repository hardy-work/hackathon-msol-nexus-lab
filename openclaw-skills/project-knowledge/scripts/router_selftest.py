#!/usr/bin/env python3
"""Offline tests for the Haiku route contract (never calls the network)."""
from __future__ import annotations

import router


CASES = [
    ('{"route":"structured","confidence":0.98,"reason":"task lookup"}', "structured"),
    ('prefix {"route":"open","confidence":0.8,"reason":"needs synthesis"} suffix', "open"),
    ('{"route":"graph","confidence":0.9,"reason":"multi-hop relation"}', "graph"),
    ('{"route":"action","confidence":"0.9","reason":"write request"}', "action"),
]


def main() -> int:
    failures = []
    for text, expected in CASES:
        got = router.parse_response(text)
        if got is None or got.route != expected:
            failures.append((text, expected, None if got is None else got.route))

    for text in ("not json", '{"route":"unknown","confidence":1}', "{}"):
        if router.parse_response(text) is not None:
            failures.append((text, "None", "accepted"))

    heuristics = {
        "Cập nhật task API Login thành Done": "action",
        "Tại sao Sprint 1 bị chậm?": "open",
        "Ai phụ trách API Login?": "structured",
    }
    for query, expected in heuristics.items():
        got = router.heuristic_route(query).route
        if got != expected:
            failures.append((query, expected, got))

    # Bậc 1 chọn sheet: TẤT ĐỊNH và chạy TRƯỚC mọi bậc khác, nên định tuyến sai ở đây
    # không bậc nào cứu được. `cong viec` từng một mình kéo mọi câu hỏi nhân sự vào
    # bảng Sprint 1 và trả về `in_kb` — tự tin và sai domain, tệ hơn hẳn im lặng.
    import answer

    sheet_cases = {
        # KHÔNG được vào bảng: 'công việc' là từ thông dụng, không phải tín hiệu task.
        "Thủ tục bàn giao công việc khi nghỉ việc thế nào?": [],
        "Người lao động có nghĩa vụ gì với công việc được giao?": [],
        "Nội quy quy định gì về công việc ngoài giờ?": [],
        # PHẢI vào bảng: có tín hiệu mạnh, hoặc từ yếu đi kèm tên trường của bảng.
        "TaskID AU-1 là gì?": ["nexus-sprint1"],
        "Sprint 1 có bao nhiêu task?": ["nexus-sprint1"],
        "Công việc nào đang ở trạng thái In progress?": ["nexus-sprint1"],
        "Task API Login có priority bao nhiêu?": ["nexus-sprint1"],
    }
    for query, expected in sheet_cases.items():
        got = answer.inferred_docs(query)
        if got != expected:
            failures.append((query, expected, got))

    if failures:
        for case in failures:
            print(f"✗ router case: {case}")
        return 1
    print(f"✓ router self-test: "
          f"{len(CASES) + 3 + len(heuristics) + len(sheet_cases)} cases qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
