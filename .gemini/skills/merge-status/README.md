# Merge Status

![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> One-command PR / CI / merge-drift checks for the RTE seat: "is commit X on main?", "is PR N open
> or merged?", "is my branch behind its target?" — each in a single tool call whose exit code is
> the answer.

## Purpose

Polling a merge used to cost a fetch→log→pr-view→read→interpret ritual per question, which burns
the seat's turn ceiling. This skill collapses each question into one call that answers through its
exit code, so an RTE can decide whether to keep waiting or hand off without spending turns on
interpretation.

## Usage

Use whenever you need the state of a PR, a merge, or CI without changing anything.
See [SKILL.md](SKILL.md) for the individual checks and their exit-code contract.

## License

MIT (see the `license` field in [SKILL.md](SKILL.md)).
