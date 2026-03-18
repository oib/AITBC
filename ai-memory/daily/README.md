# Daily Memory Directory

This directory stores append-only daily logs of agent activities.

Files are named `YYYY-MM-DD.md`. Each entry should include:
- date
- agent working (aitbc or aitbc1)
- tasks performed
- decisions made
- issues encountered

Example:
```
date: 2026-03-15
agent: aitbc1
event: deep code review
actions:
  - scanned for bare excepts and print statements
  - created issues #20, #23
  - replaced print with logging in services
```