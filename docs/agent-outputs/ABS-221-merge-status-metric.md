# ABS-221 — merge-status skill: Vorher/Nachher-Metrik (AC4)

**Datum:** 2026-07-12 · **Ticket:** ABS-221 (Parent ABS-217) · **Seat:** be-developer
**Skill:** `harness/claude/skills/merge-status/` (Quelle) + `.claude/skills/merge-status/` (Apply, release-materialisiert — s.u.)

---

## Kernmetrik: Tool-Calls pro Status-Frage

Das Turn-Ceiling des RTE (60) wird von **Status-Polling** gefressen. Die Metrik ist
**Tool-Calls pro beantworteter Status-Frage** — je weniger, desto weniger Turn-Fraß.

| Status-Frage | VORHER (Ritual) | NACHHER (merge-status) |
|---|---|---|
| Ist Commit X auf `main`? | `git fetch` + `git log`/`ls-remote` + lesen + interpretieren (~3–4 calls) | `merge-status.sh on-target X` — **1 call, Exit-Code** |
| Ist PR N offen/gemerged? | `bb pr view` + Ausgabe lesen + interpretieren (~2 calls) | `merge-status.sh pr-state N` — **1 call, Exit-Code** |
| Ist CI grün auf PR N? | `bb pr checks` + Ausgabe lesen (~2 calls) | `merge-status.sh pr-ci N` — **1 call, Exit-Code** |
| Rebase-Drift zum Ziel-Branch? | `git fetch` + `git log --oneline` + zählen (~2–3 calls) | `merge-status.sh drift B [tgt]` — **1 call, Exit-Code** |

Zusätzlicher Hebel (nicht nur Call-Zahl): der **Exit-Code IST die Antwort**, d.h. es
entfällt der teure Schritt "Ausgabe wieder einlesen und interpretieren" — genau der
Schritt, der pro Frage einen weiteren Assistant-Turn kostet.

## VORHER-Baseline (gemessen, Mining-Durchlauf 2026-07-12)

Aus dem in ABS-217 dokumentierten Mining-Durchlauf (237 Seat-Sequenzen + 962
Transcripts), RTE-Rolle, über wenige Sessions:

- `git log` — **25×**
- `git fetch` — **7×**
- `git ls-remote` — **4×**
- `bb pr view` — **4×**
- `bb pr list` — **3×**

Summe der reinen Status-Kommandos: **43** Aufrufe. Launcher-Kommentar: Turn-Ceiling
RTE=60 gesetzt, weil "CI-Polling frisst Turns". Diese Zahlen sind die Vorher-Referenz.

## NACHHER-Metrik: Messmethode (abhängig von ABS-218)

Der Miner (`scripts/skill-mining.sh`, **ABS-218**) ist zum Zeitpunkt dieser Story noch
`Ready for Development` (nicht gemerged). Der PO-Entscheid auf ABS-217 hält fest: die
Skill-Stories dürfen **parallel** zum Miner laufen, nur ihre **AC4-Verifikation** braucht
ihn; die Baseline liegt bereits persistent in den vorhandenen Run-Logs. Deshalb ist die
Nachher-Zahl hier **nicht erfunden**, sondern als reproduzierbare Messung spezifiziert:

Sobald ABS-218 gemergt ist, auf den ersten RTE-Runs *nach* Einführung des Skills:

```bash
# per-Rolle-Report, RTE-Zeile, Vorher/Nachher-Vergleich der Status-Kommandos
scripts/skill-mining.sh --role rte            # (Kommandoname/Flags per ABS-218)
```

Erwartungswert (Verdikt): die Roh-`git log`/`git fetch`/`git ls-remote`/`bb pr view`
/`bb pr list`-Häufungen kollabieren, ersetzt durch `Bash(merge-status.sh …)`-Calls im
Verhältnis ~1 Call je Status-Frage statt 2–4. Erfolgsschwelle: die vier obigen
Roh-Kommando-Zähler sinken deutlich, `merge-status`-Nutzung erscheint in der RTE-Zeile.

Solange ABS-218 nicht gemergt ist, bleibt die Nachher-Zahl offen und darf **nicht** als
gemessen behauptet werden (Evidenz-Disziplin).

## AC2-Beleg: alle Rezepte real ausgeführt (Standard PR #153)

PR #153 = `feat(skills): /run-boilerplate` — Zustand `MERGED`, merge_commit `8c67ef297ac0`.

| Kommando | Ausgabe | Exit |
|---|---|---|
| `merge-status.sh pr-state 153` | `PR 153: MERGED` | 0 |
| `merge-status.sh pr-ci 153` | `PR 153 CI: successful=0 failed=0 pending=0` | 2 (no checks) |
| `merge-status.sh on-target 8c67ef297ac0` | `ON-TARGET: … is on origin/main` | 0 |
| `merge-status.sh on-target <unmerged-sha>` | `NOT-ON-TARGET: …` | 1 |
| `merge-status.sh drift 8c67ef297ac0 main` | `DRIFT: … is 8 commit(s) behind origin/main` | 1 |

Rohe `bb`-Rezepte ebenfalls real geprüft: `bb pr view 153 --json --jq '.state'` → `MERGED`;
`.merge_commit.hash` → `8c67ef297ac0`; `bb pr checks 153 --json --jq '.summary …'` → `0 0 0`;
`bb pr list --json --jq '.pullRequests[] | .id'` (default OPEN; MERGED-Filter liefert 154,153,…).

## Architekten-Kurzentscheid (AC1)

**Neuer, dedizierter Skill `merge-status`** — KEINE Erweiterung von `release-patterns`.
Begründung: `release-patterns` triggert auf den *Handlungs*-Workflow (PR anlegen / CI
validieren / mergen); `merge-status` triggert auf die *read-only Status-Frage* ("ist X
gemerged? bin ich behind?"). Getrennter Trigger + Single-Responsibility → bessere
Auffindbarkeit (relevant für Schwester-Story ABS-223 Skill-Trigger-Audit) und je Skill
ein fokussierter Zweck. Placement analog PR #153 (run-boilerplate): Quelle in
`harness/claude/skills/`, Apply-Kopie `.claude/skills/` wird beim `/release` aus dem Tag
materialisiert (`generate-governor.sh`; die live `.claude/` ist kein handgepflegter
Byte-Copy, sondern Tag-generiert — ADR-A-0016 / CLAUDE.md Governance-Provenance).
