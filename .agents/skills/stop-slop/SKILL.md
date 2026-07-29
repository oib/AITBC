---
name: stop-slop
description: >
  Output-quality gate against AI "slop". Use before returning any substantial
  written or code deliverable — a spec, PR description, doc, review summary, or
  multi-paragraph answer — to strip filler, AI tells, unverified claims,
  invented APIs, and unrequested scope.
---

# Stop Slop

> Vendored verbatim from https://github.com/hardikpandya/stop-slop (MIT, see LICENSE in this
> directory). Only the frontmatter was adapted to this provider's skill conventions; the body and
> `references/` files are unchanged upstream content.

Eliminate predictable AI writing patterns from prose.

## Core Rules

1. **Cut filler phrases.** Remove throat-clearing openers, emphasis crutches, and all adverbs. See [references/phrases.md](references/phrases.md).

2. **Break formulaic structures.** Avoid binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency. See [references/structures.md](references/structures.md).

3. **Use active voice.** Every sentence needs a human subject doing something. No passive constructions. No inanimate objects performing human actions ("the complaint becomes a fix").

4. **Be specific.** No vague declaratives ("The reasons are structural"). Name the specific thing. No lazy extremes ("every," "always," "never") doing vague work.

5. **Put the reader in the room.** No narrator-from-a-distance voice. "You" beats "People." Specifics beat abstractions.

6. **Vary rhythm.** Mix sentence lengths. Two items beat three. End paragraphs differently. No em dashes.

7. **Trust readers.** State facts directly. Skip softening, justification, hand-holding.

8. **Cut quotables.** If it sounds like a pull-quote, rewrite it.

## Quick Checks

Before delivering prose:

- Any adverbs? Kill them.
- Any passive voice? Find the actor, make them the subject.
- Inanimate thing doing a human verb ("the decision emerges")? Name the person.
- Sentence starts with a Wh- word? Restructure it.
- Any "here's what/this/that" throat-clearing? Cut to the point.
- Any "not X, it's Y" contrasts? State Y directly.
- Three consecutive sentences match length? Break one.
- Paragraph ends with punchy one-liner? Vary it.
- Em-dash anywhere? Remove it.
- Vague declarative ("The implications are significant")? Name the specific implication.
- Narrator-from-a-distance ("Nobody designed this")? Put the reader in the scene.
- Meta-joiners ("The rest of this essay...")? Delete. Let the essay move.

## Repo-Specific Additions

Beyond the prose rules above, "slop" in this boilerplate also means unverified or padded work
product. Before handoff, confirm:

- No invented facts, file paths, functions, flags, or APIs — every named identifier is verified
  against the repo before it is stated.
- No unrequested scope — deliver what the ticket's acceptance criteria require, nothing adjacent.
- No fake evidence — never claim a command ran, a test passed, or a file exists without having
  verified it.
- Match the surrounding style — comment density, naming, and formatting of the existing code.

## Scoring

Rate 1-10 on each dimension:

| Dimension | Question |
|-----------|----------|
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50: revise.

## Examples

See [references/examples.md](references/examples.md) for before/after transformations.

## License

MIT — see [LICENSE](LICENSE). Vendored from https://github.com/hardikpandya/stop-slop.
