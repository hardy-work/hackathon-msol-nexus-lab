# Claude adapter for Project Knowledge

Use the skill entrypoint instead of duplicating the retrieval logic (run from
`openclaw-skills/project-knowledge`):

```bash
python3 scripts/run.py \
  --project nexus \
  --query "<user question>"
```

The command returns JSON. Preserve these fields in the Claude response:
`status`, `answer`, `confidence`, `citations`, `reason`, `tier`, optional
`route`, `freshness`, `knowledge_version`, `knowledge_as_of`, and
`suggested_actions`.

Default to deterministic mode. Set `PROJECT_KNOWLEDGE_LLM=1` for the gateway,
or pass `--llm` explicitly, only when Claude runtime/network is configured and
the query is open-ended. `--no-llm` forces deterministic mode. Claude may rewrite the answer for tone,
but must not change numeric values, citations, confidence, or the distinction
between `not_in_kb` and `confident_no`.

If `freshness.state` is `stale` or `unknown`, preserve the warning and ask the
operator to rebuild the corpus before using the answer for a new decision.

This adapter is read-only. If `suggested_actions` is non-empty, check the
proposal's `required_permission`, ask for explicit approval, and pass it to a
separate Jira/Excel action tool. Never call an external write API directly from
Project Knowledge.
