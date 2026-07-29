# Live-Run ABS-129 — README-Badge Auto-Stamp (2026-07-07, v2.21.1)

**Ergebnis: BESTANDEN.** Das parentless Ticket ABS-129 (Release-Tooling stampt den README-Versions-Badge
automatisch) lief die komplette Path-A-Pipeline durch: Intake-Klassifikation → PO-Triage → be-developer
(mit einem Turn-Cap-Crash + Session-Resume) → SA Stage-1 (APPROVED, keine Bounce) → QAS (APPROVED,
Parity-Suite 4/4) → PO-Acceptance (accept) → RTE/PR #56 → **Human-Merge (main `82f92ce`)** → tech-writer
(Docs, Nachzügler-PR #60).

## Zeiten (aus work/.orchestrator/run.log)

| Step | Dauer | Kosten |
|------|------:|-------:|
| po-agent Intake + Triage | 1m55s | $0.49 |
| SKIP-FORWARD Design→Ready-for-Development (Runner) | 17s | – |
| be-developer Versuch 1 (Turn-Cap-Crash bei 12 Turns) | 6m29s | $2.01 |
| _[Session-Abbruch + Stale-Lock-Stau — Infra, keine Arbeit]_ | 36m33s | – |
| be-developer Resume (verifiziert, committet `06d8dce`) | 44s | $0.52 |
| system-architect Stage-1 Review | 2m45s | $1.10 |
| qas (Parity-Suite 4/4 PASS) | 4m41s | $0.59 |
| po-agent Acceptance | 1m58s | $0.45 |
| rte → PR #56 | 3m45s | $0.54 |
| _[Human-Merge-Gate PR #56 — Wartezeit]_ | 2h49m25s | – |
| tech-writer → Docs PR #60 | 4m0s | $0.66 |
| **Wall-Clock (Spawn 1 → letzter Handoff)** | **3h57m16s** | **$6.36** |
| **davon aktive Agentenzeit (9 Spawns)** | **~26m34s** | |

Netto-Pipelinearbeit ohne Human-Gate und Infra-Stau: **~26 Minuten**.

## Operator-Eingriffe

1. Alle 6 Handoff-Transitionen manuell angewendet (Runner wendet sie weiterhin nicht selbst an —
   Befund 4 aus dem ABS-126-Run unverändert): Backlog→Design, →Ready for Development (SKIP-FORWARD
   durch Runner), →In Review, →In Test, →Story Acceptance, →Merging, →Ready for Merge; Done via Merge.
2. Allowlist vor-provisioniert nach `tmp/ABS-129-work/.claude/settings.local.json`
   (+ worktree-sichere `scripts/**`- und `README.md`-Freigabe).
3. Ready-for-Merge-Parken statt rte-Redispatch-Loop (Befund 7).
4. Stale-Lock + Backoff-Marker nach Session-Abbruch von Hand entfernt (neuer Befund, s.u.).

Positiv gegenüber ABS-126: der rte-Seat konnte `git push` + `bb pr create` diesmal **selbst**
(kein push/PR-Assist nötig).

## Neuer Befund (kritisch) — Stale-Lock blockiert Reconciliation

Ein durch Session-Abbruch (17:52→18:29) verwaister be-developer-Spawn hinterließ
`work/.orchestrator/locks/ABS-129/` + `backoff-ABS-129`. Der neu gestartete Loop pollte 100+ Zyklen
ohne einen Spawn: die Reconciliation überspringt gelockte Tickets (`orchestrator.sh:2175`,
`candidate=0` bei vorhandenem `lock_dir_for`), **ohne die TTL-Reclaim-Prüfung** — diese sitzt nur in
`acquire_lock` (`:1906`), das für ein gelocktes Ticket nie erreicht wird. Ergebnis: Deadlock trotz
längst abgelaufenem `ORCH_LOCK_TTL` (30 min). Workaround: `rmdir locks/ABS-129 && rm backoff-ABS-129*`
(nur bei nachweislich totem Seat). → Kandidat für Hardening-Iteration 3, thematisch bei ABS-133.

## Turn-Cap-Lehre

Das Default `ORCH_MAX_TURNS=12` schnitt den be-developer mitten in der AC-Verifikation ab (Arbeit lag
uncommitted im Worktree → 2 Crash-Marker, ~$2 verbrannt). Mit `ORCH_MAX_TURNS_BE_DEVELOPER=50`
(+ `ORCH_MAX_TURNS=30`) und Session-Resume war der Seat in 44s fertig. Empfehlung: höheres
Default-Turn-Ceiling für Implementier-Seats.
