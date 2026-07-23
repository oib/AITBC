# Writing AITBC Documentation

This guide keeps the AITBC documentation consistent, discoverable, and free of broken links.

## Where to put new docs

- Feature docs: `docs/features/<feature-slug>.md` (see `feature-template.md`)
- Application/service docs: `docs/apps/<area>/<service>.md`
- Release notes: `docs/releases/<version>/`
- Developer how-to's: `docs/development/`
- Operational runbooks: `docs/operations/` or `docs/deployment/`

## Feature doc structure

Use `docs/meta/feature-template.md` as the starting point for every `docs/features/*.md` file. The standard sections are:

1. Title and one-paragraph description
2. Status and release metadata
3. Implementation Details
4. Examples (CLI, API, code)
5. Operational Notes

## Link rules

- Prefer relative `.md` links over absolute paths.
- Run the link checker before committing.
- If a target file is removed, either replace the link or convert it to plain text.

## Checking links

```bash
cd /opt/aitbc
bash scripts/validate_docs.sh
```

The checker is also wired into the pre-commit hook (`validate-documentation-links`).

## Keeping docs in sync

- Add a `docs/features/<slug>.md` when a new feature is merged.
- Update `docs/FEATURES.md` if a feature changes status or release.
- Delete or archive stale docs rather than leaving broken links behind.
