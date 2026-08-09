# Training artifact contract

## Source record

The generator accepts only Markdown wiki pages with YAML frontmatter containing `page`, `name` or an H1, `visibility`, and either `doc_id` or `raw_paths`. A source citation is rendered as:

`wiki/<area>/<file>.md` · `doc_id=<id>` · `version=<n>` · `visibility=<value>`

OCR-backed pages must also carry the warning from the source page. The generator never copies the original binary into a training artifact.

## Module record

Each module has:

- a stable id and title;
- audience and learning outcome;
- source-backed key points;
- a practical activity that is explicitly labelled as a suggested activity;
- one or more citations;
- a `coverage` value: `covered`, `partial`, or `not_in_kb`.

## Review checklist

- Confirm the learner role and project before publishing.
- Verify every policy claim against the current internal document.
- Verify project dates, people and effort against the current project wiki/facts.
- Keep OCR caveats and version numbers visible.
- Ask HR/PM to resolve missing or conflicting information.
- Store the generated artifact outside the project-knowledge corpus unless the owner explicitly approves a separate ingest.
