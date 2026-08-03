#!/usr/bin/env python3
"""Format Project Knowledge JSON as Slack Block Kit-compatible JSON."""
from __future__ import annotations

import json
from typing import Any


STATUS_LABEL = {
    "in_kb": "CÓ",
    "confident_no": "CHẮC CHẮN KHÔNG",
    "not_in_kb": "KHÔNG TÌM THẤY",
    "error": "LỖI",
}


def slack_text(value: str) -> str:
    """Keep Markdown readable in mrkdwn without changing numeric content."""
    return value.replace("**", "*")


def format_result(result: dict[str, Any], thread_ts: str = "") -> dict[str, Any]:
    status = result.get("status", "error")
    label = STATUS_LABEL.get(status, status.upper())
    answer = slack_text(str(result.get("answer", "")))
    confidence = result.get("confidence", "none")
    blocks: list[dict[str, Any]] = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{label}*\n{answer}"},
    }]

    citations = result.get("citations") or []
    if citations:
        cites = "\n".join(f"• `{slack_text(str(c))}`" for c in citations)
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"*Nguồn:*\n{cites}"},
        ]})
    reason = str(result.get("reason", "")).strip()
    if reason:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"*Độ tin cậy:* `{confidence}` · {slack_text(reason)}"},
        ]})
    else:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"*Độ tin cậy:* `{confidence}` · bậc `{result.get('tier', 0)}`"},
        ]})

    actions = result.get("suggested_actions") or []
    if actions:
        for index, action in enumerate(actions):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Đề xuất action — cần bạn xác nhận:*\n" + slack_text(str(action.get("description", "")))},
            })
            blocks.append({
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Approve"},
                     "style": "primary", "action_id": f"project_action_approve_{index}",
                     "value": json.dumps(action, ensure_ascii=False)},
                    {"type": "button", "text": {"type": "plain_text", "text": "Reject"},
                     "style": "danger", "action_id": f"project_action_reject_{index}",
                     "value": json.dumps(action, ensure_ascii=False)},
                ],
            })

    response: dict[str, Any] = {
        "response_type": "in_channel",
        "blocks": blocks,
        "metadata": {
            "status": status,
            "confidence": confidence,
            "citations": citations,
            "tier": result.get("tier", 0),
            "project": result.get("project", "nexus"),
        },
    }
    if thread_ts:
        response["thread_ts"] = thread_ts
    return response
