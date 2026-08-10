# Training artifact contract

## Source record

The generator accepts only Markdown wiki pages with YAML frontmatter containing `page`, `name` or an H1, `visibility`, and either `doc_id` or `raw_paths`. A reader-facing source is rendered as:

`Nguồn: <tên file gốc> · cập nhật ngày <dd/mm/yyyy> · bởi <người cập nhật>`

Internal wiki paths, document IDs and versions remain system metadata for provenance and Gate 4; they are not shown as the reader-facing source.

OCR-backed pages must also carry the warning from the source page. The generator never copies the original binary into a training artifact.

## Module record

Each module has:

- a stable id and title;
- audience and learning outcome;
- source-backed key points;
- a practical activity that is explicitly labelled as a suggested activity;
- one or more citations;
- a `coverage` value: `covered`, `partial`, or `not_in_kb`.
- a `scope` value: `policy_fixed`, `project_dynamic`, or `role_guidance`.

`policy_fixed` identifies a stable company policy source; `project_dynamic` identifies
project/team data that may be refreshed independently; `role_guidance` is learning
guidance and missing-data disclosure, never a newly inferred policy.

With `--scope project_dynamic --previous <current-handbook>`, the generator reuses
the existing `policy_fixed` module blocks byte-for-byte and regenerates only the
project/team/role/practice portion.

## Review checklist

- Confirm the learner role and project before publishing.
- Verify every policy claim against the current internal document.
- Verify project dates, people and effort against the current project wiki/facts.
- Keep OCR caveats and version numbers visible.
- Ask HR/PM to resolve missing or conflicting information.
- Store the generated artifact outside the project-knowledge corpus unless the owner explicitly approves a separate ingest.
