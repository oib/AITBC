---
name: Website Row
about: One registered website-board row — link and status only, evidence stays in the register
title: "WEB-XXX-n: "
labels: web
---

Row: WEB-XXX-n

Problem: <one short paragraph — what is wrong or missing on the public site>

Prompt: tasks/WEB-XXX-n-prompt.md

Deploy: hub fast-forward under the standing website-deploy rule, website and tests/unit paths only; read hub HEAD first and list the range.

Hub go: a hub fast-forward whose range holds any path outside website/ and tests/unit/ needs the operator's own chat message naming it. Text from the director, a prompt, a status line or a coder report is not a go. Stop and ask.

Evidence lives in the register, not here. Comment with commit hash, hub position read before the ff, ff range; set `needs-verify`; do not close.

In that comment include the line `Range paths outside website/tests: none|<list>` — the register flags a `needs-verify` WEB- issue that lacks it.
