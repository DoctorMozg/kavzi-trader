# pipeline-coder memory

- [Filter config wiring](filter_config_wiring.md) — A filter tunable lives in 3 coordinated places; removing one means all three.
- [Confluence override contract](confluence_override_contract.md) — get_confluence_override returns int|None; callers gate on `is not None`, so dropping a branch to None is behavior-safe.
- [Risk validator conventions](project_risk_validator.md) — how DynamicRiskValidator checks are structured, wired, and fail-closed.
- [Pre-commit gotchas](feedback_precommit_gotchas.md) — pre-commit runs --all-files; pre-existing lint errors in untouched files are not your scope.
