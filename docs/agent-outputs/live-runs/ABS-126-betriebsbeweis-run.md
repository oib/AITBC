# Live-Run ABS-126 — Betriebsbeweis v2.21.0 (2026-07-07)

**Ergebnis: BESTANDEN mit Operator-Assists.** Das parentless Ticket ABS-126 (assign-Kommando +
Assignee beim Spawn + Direkt-Impl-SOP) lief 15:15–17:27 UTC durch die komplette Path-A-Pipeline:
Intake-Klassifikation → PO-Triage → be-developer → SA-Review (1 Bounce + Fix) → QA (APPROVED,
139/139 + Test 8c 4/4, 0 Regressionen) → PO-Acceptance (accept) → RTE/PR → Human-Merge (PR #54,
main `8bde05a`, Governor v2.21.1) → tech-writer (Docs, Nachzügler-PR #55). Alle v2.21.0-Features
live gesehen: Intake-Klassifikation (Path A), Worktree-Spawns, Session-Resume, Handoff-Repair,
Modell-Label, Usage-/Tool-Telemetrie, Follow-up-Watcher, per-Ticket-Lock.

**Kosten:** ~$14 über ~16 Spawns (davon ~$3 Leerlauf-Respawns). **Dauer:** ~2h 12min inkl.
Human-Gate-Wartezeit.

## Operator-Eingriffe (7)

1. Backlog→Ready for Development, In Review, In Progress (Bounce), In Test, Story
   Acceptance (Korrektur), Ready for Merge — 6 Transitionen manuell ausgeführt.
2. Allowlist in den Worktree provisioniert (`tmp/ABS-126-work/.claude/settings.local.json`).
3. Steering-Kommentar (Unblock-Notification) nach Allowlist-Fix.
4. git push + `bb pr create` für den rte-Seat (PR #54) und den tech-writer-Nachzügler (PR #55).

## Retro-Befunde (Kandidaten für Hardening-Iteration 3)

1. **Worktree-Spawns ohne Allowlist** (KRITISCH): `ORCH_WORKTREE_SPAWNS=1` setzt den Seat-cwd auf
   den Worktree; `.claude/settings.local.json` ist uncommitted und reist nicht mit → alle
   Write/Edit denied, Seat komponiert Implementierung als Jira-Kommentar. Fix: Runner kopiert
   settings.local.json (+ ggf. worktree-sichere `scripts/**`-Freigabe) beim Provisioning.
2. **Packet-Anomalie `from_status`**: Resume-Packet trug "Ready for Epic Acceptance" (Epic-Status
   von ABS-114) an einem Story-Ticket — Packet-Construction referenziert falsches Ticket.
3. **Bash-Denials uneinheitlich je Seat**: po-agent/be-developer/system-architect/rte konnten
   Adapter-Kommandos (comment/transition) und push/bb NICHT ausführen; bsa/qas/po-agent
   (Acceptance) konnten es. Ursache klären (Command-Shape? mehrzeilige --body? cwd?).
4. **Runner wendet Handoff-Transition nicht selbst an**: geparster Handoff mit klarem Zielstatus
   führt NICHT zur Transition; stattdessen endlose Resume-Respawns auf unverändertem Status,
   ohne Eskalation (kein Erkennungsmuster "Handoff ok, Status unverändert, n Zyklen"). Teuerster
   Einzelbefund (Leerlauf-Spawns à $0.2–0.8).
5. **SKIP-LOCKED-Events gehen auf Rest-Status verloren**: tech-writer-Dispatch auf Done wurde
   wegen Lock übersprungen; Done ist legit-rest → Reconciliation holt den Dispatch nie nach.
6. **qas-Transition übersprang Stationen**: In Test → Done direkt (statt Story Acceptance →
   Merging → Docs); Operator-Korrektur nötig.
7. **Merging ist kein Rest-Status**: Reconciliation re-dispatcht rte endlos, solange das
   Human-Merge-Gate offen ist; rte sollte nach PR-Erstellung selbst auf Ready for Merge gehen.
8. **model:-Label wirkt rollenblind** (Operator-Retro-Punkt): SA-Review lief wegen model:sonnet
   auf Sonnet. Enriched-Ticket liegt vor: **ABS-128** (Backlog, bewusst ohne orchestrator-ready).
9. Klein: bsa-/SA-Handoffs enthielten stale "not committed"-Behauptungen (Commit lag vor);
   tech-writer pushte seinen Docs-Commit nach dem PR-Merge (Nachzügler-PR nötig).

## Positiv

- Selbstheilung Handoff-Repair funktionierte 4/4 mal (po-agent, qas, rte, be-developer).
- Follow-up-Watcher triggerte korrekt auf kind:follow-up (n=1/5) und der bsa fixte beide
  SA-Findings eigenständig im Worktree inkl. Regressionstest (Commit 68a3976).
- Telemetrie (ABS-125) lieferte auf jedem Spawn Usage + Tool-Zählung; MODEL-LABEL-Events sichtbar.
- Kill-Switch-Drain sauber (Run-Ende 17:28 UTC, Cycle ~500).
