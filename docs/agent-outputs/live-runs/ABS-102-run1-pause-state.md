# ABS-102 Live-Run 1 — Pause-Snapshot (2026-07-06 ~17:15 UTC)

Erster Jira-backed Live-Lauf des Orchestrators (ABS-101 Label-Gate-Test, eskaliert zum
vollen Epic-Durchlauf). **Vom Operator pausiert**, um Retro-Fixes einzubauen, bevor der
Rest des Story-Fan-outs läuft. Wiederaufnahme: Orchestrator mit demselben Rezept starten
(siehe "Resume-Rezept" unten) — die Startup-Reconciliation nimmt alle ruhenden Tickets
automatisch wieder auf.

## Pipeline-Stand (Jira, Projekt ABS)

| Ticket | Status | Arbeit |
|---|---|---|
| ABS-102 (Epic) | Stories In Flight | JOIN wartet auf alle Children Done |
| ABS-103 Spec + PATH_DECISIONs | Ready for Development | Spec fertig komponiert im geblockten Versuch (nur als Session-Inhalt, NICHT auf Disk); Neuanlauf nötig — Write auf specs/** ist inzwischen erlaubt |
| ABS-104 Intake-Klassifikation | Ready for Development | Branch `ABS-104-intake-classification` (leer); Worktree `tmp/ABS-104-work` vorbereitet + TDM-Hinweis auf Ticket |
| ABS-105 Path-A Solo-Pipeline | Ready for Development | Worktree `tmp/ABS-105-work` (Branch `ABS-105-parentless-solo-pipeline`) vorbereitet + TDM-Hinweis |
| ABS-106 Path-A Tail (PR-to-main) | Ready for Development | Branch `ABS-106-path-a-tail-pr-to-main` mit Arbeit; Handoff erfolgt, Transition fehlte |
| ABS-107 Path-B DoR-Entry-Gate | Ready for Development | Branch `ABS-107-path-b-dor-entry-gate`; Handoff erfolgt, Transition fehlte |
| ABS-108 Path-B Rework-Loop | Ready for Development | **Arbeit committet** auf `ABS-108-path-b-autofix-rework-loop` (2 Dateien, "Implementation Complete"), aber Crash-Marker weil Handoff-Format nicht parsebar; 1 SPAWN-CRASH-Marker |
| ABS-109 Diagramm + SOPs | **In Test** | Voll durch Dev + Architekten-Review (Verdict pass 17:09Z); Branch `ABS-109-intake-heads-diagram-sop` (Commit f7c3ef6); nächster Seat: qas |
| ABS-110 E2E-Szenarien | Ready for Development | 1 SPAWN-CRASH-Marker (Operator-Kill-Artefakt); TDM-Hinweis auf Ticket |

## Lokaler Repo-Zustand

- Haupt-Tree: `main` (sauber bis auf Folgendes)
- Uncommitted: `scripts/jira-tracker.sh` (Endpoint-Migration `/search/jql`, HTTP-410-Fix + spätere User-Änderung), `.claude/settings.local.json` (Allowlist: jira-tracker, Shell-Basics, Write-Pfade tmp/specs/docs/tests)
- Untracked Agent-Artefakte: `work/story1body.md`, `docs/agent-outputs/qa-validations/ABS-102-qa-validation.md`, `tmp/ABS-109-changelog-entry.yml`, `tmp/HARNESS_CHANGELOG.new.yml`
- Worktrees: `tmp/ABS-104-work`, `tmp/ABS-105-work`
- Story-Branches: ABS-104/106/107/108/109 (s. Tabelle)

## Timing-Analyse (aus Jira-Kommentar-Timestamps, 84 Events 14:34–17:11 UTC)

- Epic-Pipeline Backlog→Stories In Flight: **61 min** (14:34–15:35), davon ~25 min
  Verlust durch Enrichment-Turn-Decke (2 Crashes) und ~10 min Architekten-Schleife
  (Compound-Command-Denial), aufgelöst durch Operator-Release.
- Story-Phase (8 Stories, seriell): **96 min** für 1 komplett durchgelaufene Story
  (ABS-109 bis In Test) + Teilarbeit an 4 weiteren. Taktung: 1 Spawn zu jeder Zeit,
  6–15 min pro Spawn, ~50 % der Spawns waren Duplikate/geblockt.
- Größte Einzel-Gaps: 12,3 min (ABS-109 Dev), 15,6 min (ABS-107), 11,6 min (ABS-108),
  10,7/10,8/9,4 min — jeweils genau ein serieller Spawn.

## Root Causes → Retro-Fixes (priorisiert)

1. **Keine echte Parallelität** — `run_spawn_cmd` blockiert den Poll-Loop; `ORCH_MAX_CONCURRENT=3` wirkungslos. Fix: asynchrone Spawns + Lock-basierte Koordination.
2. **Handoff-Format-Strenge erzeugt Phantom-Crashes** — echte, committete Arbeit wird als "spawn failed" gewertet, wenn der Abschlusstext kein parsebares `## Handoff` enthält → Doppel-Spawns, Crash-Marker. Fix: Erfolg zusätzlich an Status-Transition/Commit-Evidenz messen; Handoff-Format im Packet-Prompt hart vorgeben.
3. **Write-Boundary vs. Implementierungs-Stories** — Seats müssen `scripts/**` ändern, dürfen es im Haupt-Tree nicht; Agents nutzen von sich aus keine Worktrees und schalten stattdessen den Haupt-Checkout um. Fix: Worktree-Protokoll (`git worktree add tmp/<ticket>-work`) verbindlich ins Packet/Agent-Prompt; Haupt-Checkout-Switch verbieten.
4. **`depends_on` wird nicht ge-gated** — Runner dispatcht Ready-for-Development in beliebiger Reihenfolge (grep depends_on in orchestrator.sh: 0 Treffer). Fix: Dispatch prüft depends_on gegen Status der Referenzen.
5. **Kein timestamped globales Log** — orchestrator-Log ohne Timestamps, stderr der Spawns verworfen (`2>/dev/null`). Fix: ISO-Timestamps in log(), Spawn-stderr in Datei, strukturiertes Event-Log (work/.orchestrator/run.log) für Timing-Analysen.
6. **Turn-Budget nicht seat-dimensioniert** — Enrichment (8 Children) crashte 2× an ORCH_MAX_TURNS=40; 120 global ist Verschwendung für kleine Seats. Fix: per-Rolle-Override (z. B. ORCH_MAX_TURNS_ISSUE_ENRICHMENT).
7. **Jira `/search` entfernt (HTTP 410, CHANGE-2046)** — Migration auf `/search/jql` liegt uncommitted vor; braucht Commit + Test-Shim-Anpassung + PR (Task-Chip existiert).
8. **Kleineres**: ADF-Kommentare zeigen literales `\n` (Escaping im Adapter); Allowlist-Baseline für Live-Runs dokumentieren (Shell-Basics, Write-Pfade); SKIP-UNLABELLED-Log-Spam drosseln; Spawn-Versuch-1-Fehler ohne stderr nicht diagnostizierbar (siehe 5).

## Resume-Rezept

```bash
export JIRA_SITE=https://lovebytecodes.atlassian.net
export JIRA_EMAIL=mhmnn9@gmail.com
export JIRA_API_TOKEN="$(security find-generic-password -s JIRA_API_TOKEN -w)"
export JIRA_PROJECT_KEY=ABS
export JIRA_STATUS_ALIASES="Ready for Development=Selected for Development"
export JIRA_JQL_FILTER='labels = orchestrator-ready OR parent = ABS-102'
export TRACKER_CMD=scripts/jira-tracker.sh
export ORCH_STALL_EPIC_SECONDS=0 ORCH_POLL_INTERVAL=15
export ORCH_MAX_TURNS=120 ORCH_AGENT_TIMEOUT=2700 ORCH_MAX_SPAWNS_PER_RUN=50
scripts/orchestrator.sh --live
```
