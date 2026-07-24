# DAO Grants

The AITBC DAO supports builders through milestone-based grants.

## Register as a developer

Before submitting a grant proposal you must register a developer profile:

```bash
./venv/bin/aitbc developer register \
  --wallet-address 0x... \
  --name "Your Name" \
  --github your-handle
```

## Submit a grant proposal

```bash
./venv/bin/aitbc grant create \
  --title "My Project" \
  --description "One sentence summary" \
  --requested-amount 10000 \
  --voting-days 14
```

## Lifecycle

- `draft` — proposal created
- `submitted` — ready for review
- `under_review` — DAO reviewers evaluate
- `approved` — voting starts
- `active` — funds disburse as milestones complete
- `completed` — all milestones paid

## Milestones

Add milestones to a proposal to release funds incrementally:

```bash
./venv/bin/aitbc grant milestone create <grant-id> \
  --title "Milestone 1" \
  --amount 2500 \
  --due-date 2026-08-01
```

Disburse a milestone after it is approved:

```bash
./venv/bin/aitbc grant disburse <grant-id> \
  --milestone-id <milestone-id> \
  --amount 2500
```
