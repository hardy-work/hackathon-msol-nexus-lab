# Claude adapter for Project Knowledge

Use the skill entrypoint instead of duplicating the retrieval logic (run from
`openclaw-skills/project-knowledge`):

```bash
python3 scripts/run.py \
  --project nexus \
  --query "<user question>"
```

The command returns JSON. Preserve these fields in the Claude response:
`status`, `answer`, `confidence`, `citations`, `reason`, `tier`, and
`suggested_actions`.

Default to deterministic mode. Add `--llm` only when Claude runtime/network is
configured and the query is open-ended. Claude may rewrite the answer for tone,
but must not change numeric values, citations, confidence, or the distinction
between `not_in_kb` and `confident_no`.

This adapter is read-only. If `suggested_actions` is non-empty, ask for explicit
approval and pass the proposal to a separate Jira/Excel action tool. Never call
an external write API directly from Project Knowledge.
