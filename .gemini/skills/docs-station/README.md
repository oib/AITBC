# Docs Station

![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Tech-Writer recipes for the `Docs` station — verify the story's implementation PR really merged,
> edit docs on the story branch without a checkout, validate markdown, and run the Docs→Done
> exit-precondition checklist.

## Purpose

The `Docs` station is the post-merge exit of a story (ABS-266). This skill supplies its recipes:
a worktree-less merge-base gate that answers "is the implementation PR actually merged?", in-place
inspection and editing of docs on the story branch, markdown validation (markdownlint with an awk
line-length fallback when it is unavailable), and the checklist that must hold before a story may
transition to `Done`.

## Usage

Invoke at the `Docs` seat before writing docs or transitioning a story to `Done`.
See [SKILL.md](SKILL.md) for the recipes and the exit checklist.

## License

MIT (see the `license` field in [SKILL.md](SKILL.md)).
