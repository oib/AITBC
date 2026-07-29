# Retro — ABS-102-Zyklus (v2.18.0 → v2.20.0), 2026-07-06/07

Ein Abend/eine Nacht, drei Etappen: (1) erster Jira-backed Live-Run des Orchestrators
(ABS-101-Gate-Test, eskaliert zum vollen Epic-Lauf, pausiert), (2) Hardening-Epic ABS-111
direkt implementiert und als v2.19.0 released, (3) Resume-Lauf bis Epic Done + v2.20.0.
Timing-Quellen: Jira-Kommentar-Timestamps (Run 1, 84 Events) und `work/.orchestrator/run.log`
(v2.19-Läufe, 789 Zeilen).

## Kennzahlen

- **Deliverables:** Epic ABS-102 komplett (8/8 Stories Done, Epic Done), Epic ABS-111 komplett
  (12 Punkte + 8 Live-Hotfixes), 2 Releases (v2.19.0, v2.20.0), 12 PRs (#42–#52 + Hotfix-Addenda),
  Jira-first-Versionierung (v2.21.0 bereits geplant).
- **run.log (v2.19-Läufe):** 92 Spawns · 73 Handoffs · 25 Session-Resumes · 13 Handoff-Repairs ·
  16 Retries · 15 Spawn-Crashes (davon 13 = externer Rate-Limit-Sturm) · 276 DEPENDS-WAIT ·
  8 SKIP-FORWARD.
- **Durchsatz-Vergleich:** Run 1 (v2.18): 96 min für 1 Story, seriell, mit Dauerbetreuung.
  v2.19-Resume: Stories liefen in ~20–30 min durch die volle Pipeline, zeitweise 2 Seats parallel,
  inkl. zweier echter Qualitäts-Bounces und eines Sibling-Merge-Konflikts. DoD-Messlatte
  (>2× Durchsatz, <50 % Spawns pro Ergebnis) klar gehalten.
- **Tests am Ende:** orchestrator 238/238 · jira-tracker 102/102 · e2e-workflow-v3 **83→130**
  Szenarien · intake-classification 21/21 (neu) · alle grün am Release-Tag.

## Was richtig gut funktioniert hat

- **Evidenz-basiertes Fixen:** Jeder der ~14 Betriebs-Bugs wurde aus einem konkreten Live-Symptom
  diagnostiziert, minimal gefixt, getestet, committet und im PR dokumentiert — kein spekulatives
  Hardening.
- **Die Schutzketten:** Budget-Pause (ADR-A-0009) hat den Rate-Limit-Sturm sauber beendet;
  Crash-Marker/Crash-Limit, Re-Read-Guard und Single-Flight-Locks haben nie Daten verloren.
- **Session-Resume + Handoff-Repair (A2/C7):** 25 Resumes und 13 Repairs ersetzten je einen
  vollen Duplikat-Spawn — der größte Einzel-Hebel gegen Token-Verschwendung nach der Parallelität.
- **depends_on-Gate:** 276 WAIT-Intents = die Kette lief exakt in Reihenfolge; der E2E-Story-Fehlstart
  aus Run 1 trat nie wieder auf.
- **Direkt-Implementierung des Hardening-Epics** (Execution-Mode-Klausel, kein orchestrator-ready-Label):
  Das ABS-101-Gate hat das Epic zuverlässig aus der Pipeline gehalten — die Maschine konnte ihr
  eigenes Upgrade nicht anfassen.
- **Seat-Disziplin der Agents:** Blockierte Seats eskalierten mit fertigen Operator-Kommandos statt
  Workarounds ("no fabricated transition"); der RTE erkannte Branch-Kontamination selbst und
  verweigerte Inhalts-Auflösung korrekt (ADR-A-0004).
- **4 parallele Subagenten auf disjunkten Datei-Sets** beim ABS-111-Bau: null Konflikte —
  das Isolationsprinzip bewies sich beim Bauen seiner selbst.

## Was gelernt wurde (Betriebserkenntnisse, alle als Follow-ups auf ABS-111 geparkt)

1. **Gate-bei-Acceptance statt Done** (User): Docs+Merge können parallel zur nächsten Story laufen;
   erfordert Worktree-Basis = Epic-Branch (bereits teilweise gelandet).
2. **Iteration-Guard zählt falsch:** informative "Iteration N of M"-Marker in APPROVE-Kommentaren
   werden als Bounces gezählt, kein Reset → False-Positive-Dauerblock (ABS-107/109).
3. **Rate-Limit-Robustheit:** kein Backoff zwischen Crash-Zyklen; Fast-Fail-Bursts (<10s-Spawn-Tode)
   sollten als Umgebungsausfall den Loop pausieren; Eskalations-Seats dürfen nicht selbst
   crash-loopen.
4. **Session-Generationen:** resumte Sessions behalten ihren alten Permission-Kontext —
   Config-Generation-Stempel nötig, sonst bleibt eine Alt-Session dauerhaft denied.
5. **Bounce-Routing:** Reviewer bouncten nach `In Progress` (NOOP-Zeile = Dispatch-Deadlock);
   Ziel muss `Ready for Development` sein (Prompt- oder Statuses-Fix).
6. **Token-Accounting** (User): `total_cost_usd`/usage stehen im Spawn-JSON und werden verworfen —
   als run.log-Spalten wird der Kostenreport ein Einzeiler.
7. **Modell-Steuerung** (User): `model:<x>`-Label pro Ticket beim Erstellen (analog `role:`),
   Präzedenz Ticket > `ORCH_MODEL_<ROLE>` > Frontmatter; alle Seats liefen diesen Lauf auf ihren
   Frontmatter-Modellen (meist Opus) — Right-Sizing ungenutzt.
8. **Cursor Composer 2.5 als Spawn-Provider** (User): Seam ist provider-förmig; per-Rolle-Override
   (`ORCH_SPAWN_CMD_<ROLE>`), Resume-Äquivalent zu verifizieren.
9. **bb-CLI-Falle:** `bb pr merge` liefert Exit 0 bei Merge-Konflikt — auf ✓/✗-Output prüfen.
10. **Allowlist-Semantik:** Pfade sind projekt-root-relativ (Worktree ≠ Haupt-Checkout),
    Compound-Commands scheitern am schwächsten Segment, absolute Pfade matchen Literal-Patterns nicht —
    alles jetzt im SOP ("Live-Run Allowlist Baseline"), aber fehleranfällig by design.

## Was besser werden muss

- **Operator-Abhängigkeit bei Merges:** Story→Epic-Merges liefen manuell (bb-Merge bewusst nicht
  auf der Spawn-Allowlist). Kandidat: `ORCH_AUTOMERGE`-Gate (ADR-A-0014) aktivieren, sobald das
  Vertrauen da ist — der Lauf hätte dann null Operator-Touches im Happy Path.
- **Monitor-/Event-Rauschen:** Stale-Dispatch-Races nach Operator-Transitionen erzeugten
  Nachzügler-Spawns (je ein verschwendeter Seat). Re-Read-Guard könnte direkt vor dem Spawn-Exec
  ein zweites Mal prüfen.
- **Wartungsstopps:** 6 Kill-Switch-Restarts, weil Runner-Config nur beim Start gelesen wird —
  ein SIGHUP-Reload oder Config-Datei-Polling würde die Stopps eliminieren.

## Offene Fragen (Team)

- ORCH_AUTOMERGE für Story→Epic aktivieren (v2.21.0) oder weiter Operator-Merges?
- Cursor-Provider: nur mechanische Seats oder auch Implementierer?
- Gate-bei-Acceptance: als Default oder als Opt-in-Flag?

## Feiern 🎉

Ein Epic, das der Orchestrator v2.18 in Run 1 nicht über eine Story hinaus schaffte, lief unter
v2.19/v2.20 **Ende-zu-Ende selbst durch** — inklusive Rework-Schleifen, Security-Review-Stage,
Sibling-Merge-Konflikt und einem API-Totalausfall — und hat sein eigenes Test-Sicherheitsnetz
dabei von 83 auf 130 Szenarien vergrößert. Die Boilerplate hat sich in einer Nacht zweimal selbst
released, mit Versionsverwaltung aus Jira.
