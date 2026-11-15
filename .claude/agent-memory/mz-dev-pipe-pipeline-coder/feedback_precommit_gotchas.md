---
name: feedback-precommit-gotchas
description: pre-commit runs across all files; pre-existing lint errors in untouched files are out of scope
metadata:
  type: feedback
---

`uv run pre-commit run --all-files` lints the ENTIRE repo, not just your changed files. When the working tree already has unrelated uncommitted changes, pre-commit may report E501/format failures in files you never touched.

**Why:** Scope discipline — a bug fix should not drag in cleanup of unrelated files, and editing files outside the work unit pollutes the diff and risks conflicts with other in-flight work.
**How to apply:** After a full pre-commit run, attribute each failure to a file. For failures in files you did not modify, leave them alone and note them. Confirm YOUR files are clean by re-running ruff/mypy scoped to just your changed paths (`uv run ruff check <files>`, `uv run ruff format --check <files>`, `uv run mypy <file>`).
