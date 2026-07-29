# Run Status

![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Answers the operator's recurring "Status?" question in one compact reply — as an isolated fork,
> so only the short answer returns and the raw dumps stay behind.

## Purpose

Asking "where are we?" used to mean pulling board dumps, run logs, and seat state into the asking
context. This skill runs as a fork (`context: fork`, `agent: Explore`): it gathers the raw
material out of sight and returns only the situation report — what is running, what is stuck, and
what is waiting on a human.

## Usage

Invoke when the operator asks "status?", "where are we?", or "what's waiting on me?" — and from
the Ops-Sweep seat before it decides whether to act.
See [SKILL.md](SKILL.md) for the collected signals and the answer format.

## License

MIT (see the `license` field in [SKILL.md](SKILL.md)).
