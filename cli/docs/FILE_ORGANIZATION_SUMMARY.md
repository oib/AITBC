# CLI File Organization Summary (docs/)

**Updated**: 2026-06-22

This is the docs-subdirectory companion to the top-level [`../FILE_ORGANIZATION_SUMMARY.md`](../FILE_ORGANIZATION_SUMMARY.md). The authoritative, full directory tree of `cli/` lives there; this file documents what lives in `cli/docs/` and how it relates to the rest of the CLI documentation.

## Files in `cli/docs/`

| File | Purpose |
|---|---|
| `README.md` | Landing page for CLI technical documentation (this directory's index) |
| `DISABLED_COMMANDS_CLEANUP.md` | Historical analysis of previously disabled commands (hermes, marketplace_cmd, marketplace_advanced) — all have since been re-enabled or merged. Kept for historical context. |
| `FILE_ORGANIZATION_SUMMARY.md` | This file — docs-subdir organization reference |

## Relationship to other CLI docs

```
cli/
├── README.md                       # User-facing CLI overview & command reference (authoritative)
├── CLI_USAGE_GUIDE.md              # Detailed usage guide with workflows
├── FILE_ORGANIZATION_SUMMARY.md    # Full directory tree of cli/ (authoritative)
└── docs/
    ├── README.md                   # This directory's landing page
    ├── DISABLED_COMMANDS_CLEANUP.md
    └── FILE_ORGANIZATION_SUMMARY.md  # This file
```

The top-level `cli/README.md`, `cli/CLI_USAGE_GUIDE.md`, and `cli/FILE_ORGANIZATION_SUMMARY.md` are the canonical, user-facing references. The files in `cli/docs/` provide a documentation index and historical context.

## Notes

- The `DISABLED_COMMANDS_CLEANUP.md` timeline (Week 1-3 actions) is historical. The commands it discusses (`hermes`, `marketplace_cmd`) are now registered in `aitbc_cli/core/main.py` and visible via `aitbc --help`.
- The older `FILE_ORGANIZATION_SUMMARY.md` (this file's previous version) referenced files and venv sizes that no longer match the current tree. The current authoritative tree is in [`../FILE_ORGANIZATION_SUMMARY.md`](../FILE_ORGANIZATION_SUMMARY.md).

---

*Last updated: 2026-06-22*
