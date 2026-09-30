# CI/CD documentation

The earlier pipeline guide was a foreign template (Next.js/yarn, Stripe,
Linear) — deleted. The real pipeline:

- **GitHub CI**: `.github/workflows/ci.yml`
- **Gitea CI**: `.gitea/workflows/ci.yml`
- **Pre-commit gates**: `.pre-commit-config.yaml` — the same checks run
  locally (do not bypass with `--no-verify`).
- **CLI docs drift**: `scripts/generate_cli_docs.py --check`
- **Docs generation**: `scripts/docs/gen_master_index.py --check`

Contributing workflow: [CONTRIBUTING.md](../CONTRIBUTING.md).
