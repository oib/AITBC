# ABS-123 — Headless-Skill-Audit: Built-in Claude-Code-Skills/-Tools für gespawnte Seats

**Datum:** 2026-07-07 · **Branch:** ABS-114-hardening-iteration-2 · **Scope:** NUR Audit (Voll-Inventar), keine Verdrahtung.
**Methode:** Echte Test-Spawns (`claude -p … --output-format json`, Modell `claude-haiku-4-5-20251001`, max 2–4 Turns), teils direkt, teils über den echten Seam `scripts/orchestrator-spawn-claude.sh`. Alle Roh-JSONs liegen unter `/private/tmp/abs123-probe*.json`. Keine Repo-Datei außer diesem Bericht geändert; Agent-Def-Testkopie unter `/private/tmp/abs123-agents/qas-skilltest.md`.

---

## (b) Antwort auf die Kernhypothese (vorangestellt)

**Hypothese teilweise bestätigt, mit wichtiger Präzisierung:**

1. **Headless-Sessions laden Skills ganz normal.** Eine nackte `claude -p`-Session hat das `Skill`-Tool und sieht den vollen Skill-Katalog (Repo-Skills aus `.claude/skills/`, User-Skills, Commands, CLI-Built-ins wie `code-review`/`verify`/`init`). Headless ist NICHT das Problem.
2. **Die `tools:`-Frontmatter der Agent-Defs ist eine harte Allowlist.** Da `Skill` in keiner Rollen-Def steht, hat **kein gespawnter Seat heute das Skill-Tool** — der QAS-Seat meldet nur `Read, Bash` und kann weder Write noch Skill benutzen (enforced, nicht nur Self-Report). Das bestätigt den Kern der Hypothese für alle Orchestrator-Spawns.
3. **`Skill` in `tools:` genügt, um das Tool und den vollen Katalog zu erschließen** — ABER: unter dem Seam-Flag `--permission-mode dontAsk` werden **Repo-/User-Skills bei der Invocation permission-verweigert**; nur CLI-Built-ins (z. B. `verify`) laufen ohne Zusatz. Repo-Skills brauchen zusätzlich `--allowedTools "Skill"` (oder eine entsprechende settings-Allow-Regel).
4. **`anthropic-skills:*`-Plugin-Skills (docx, pdf, pptx, xlsx, …) tauchen headless NICHT auf** — sie sind an die Desktop-/Cowork-Umgebung gebunden, nicht an die CLI.

---

## (a) Inventar

### Tools (Self-Report der Session; Enforcement separat verifiziert, s. Beleg P5)

| Tool | Bare `claude -p` | Seam + `qas.md` (`tools: [Read, Bash, Grep, mcp__…]`) | Seam + Testdef `tools: [Read, Bash, Grep, Skill]` |
|---|---|---|---|
| Read | ja | ja | ja |
| Bash | ja | ja | ja |
| Write / Edit | ja | **nein** (enforced, Probe P5) | nein |
| Grep | (nicht self-reported)¹ | (nicht self-reported)¹ | (nicht self-reported)¹ |
| **Skill** | **ja** | **nein** (enforced) | **ja** |
| Agent, ToolSearch, WebFetch, WebSearch, Monitor, SendMessage, Task*, Notebook*, Artifact, Workflow, … | ja | nein | nein |
| `mcp__linear-mcp__*` (Platzhalter aus qas.md) | – | wird als Literal durchgereicht, matcht keinen Server → wirkungslos | – |

¹ `Grep` stand in allen drei Fällen in der effektiven tools-Liste, wurde aber von keinem Probe-Spawn self-reported. Vermutlich CLI-interne Darstellung (Suche via Bash/ripgrep); für die Verdrahtungsfrage irrelevant, als Anomalie notiert.

### Skills (Katalog laut Skill-Tool, identisch bare und mit `Skill` in tools:)

| Kategorie | Sichtbar headless? | Invocation unter Seam-Flags (`--permission-mode dontAsk`)? | Beispiele |
|---|---|---|---|
| Repo-Skills `.claude/skills/` (20) | ja | **NEIN — Permission-Denial**; ja mit `--allowedTools "Skill"` | jira-sop, safe-workflow, git-advanced, pattern-discovery, testing-patterns … |
| Repo-Commands `.claude/commands/` | ja (als Skills gelistet) | nicht separat getestet (gleiche Klasse wie Repo-Skills erwartet) | pre-pr, start-work, retro, release … |
| User-Skills (~/.claude) | ja | nicht getestet | bitbucket-pr, last30days, ponytail |
| CLI-Built-ins | ja | **JA, ohne Zusatz** | code-review, verify, review, security-review, init, simplify, loop, schedule, claude-api, run, deep-research, dataviz … |
| Installierte Plugins | ja | nicht getestet | claude-code-setup:claude-automation-recommender |
| **anthropic-skills:\*** (docx, pdf, pptx, xlsx, schedule, skill-creator, …) | **NEIN** | – | tauchen im headless-Katalog nicht auf |

Vollständige Katalogliste (62 Einträge): siehe `/private/tmp/abs123-probe1b-baseline-skills.json`.

### (5) Effekt der `tools:`-Frontmatter — präzise

- `tools:` ist eine **harte Allowlist**: Tool nicht gelistet → nicht sichtbar UND nicht benutzbar (Write-Versuch des QAS-Seats scheiterte real, keine Datei erzeugt; Probe P5).
- **Ein einziger Eintrag `Skill` genügt**, um das Skill-Tool samt komplettem Katalog freizuschalten (Probe P2b). Es gibt keine Granularität pro Skill über `tools:` — Granularität ginge nur über Permission-Regeln wie `Skill(name)`.
- Die Skill-**Invocation** unterliegt zusätzlich dem Permission-System: unter `--permission-mode dontAsk` (Seam-Default, Zeile 190 des Spawn-Skripts) werden Repo-Skills still verweigert (`permission_denials: [{tool_name: "Skill", skill: "jira-sop"}]`), Built-ins nicht.

---

## (c) Belege (Kommandos + JSON-Auszüge)

### P1a — Baseline-Tools (bare)
```bash
claude -p "Liste die dir verfügbaren Tools auf, nur Namen, eine Zeile pro Tool. Keine weiteren Erklärungen." \
  --output-format json --max-turns 2 --model claude-haiku-4-5-20251001
```
```json
"result": "Agent\nArtifact\nBash\nEdit\nRead\n…\nSkill\nToolSearch\nWorkflow\nWrite\n…\nMonitor\nNotebookEdit\n…\nWebFetch\nWebSearch"
```
→ `Skill` ist in der nackten Headless-Session vorhanden. (Voll: `/private/tmp/abs123-probe1-baseline-tools.json`)

### P1b — Baseline-Skills (bare)
```bash
claude -p "Welche Skills stehen dir über das Skill-Tool zur Verfügung? Gib NUR die Skill-Namen aus…" \
  --output-format json --max-turns 2 --model claude-haiku-4-5-20251001
```
→ 62 Skills: alle 20 Repo-Skills, Commands, User-Skills, Built-ins (`code-review`, `verify`, `review`, `security-review`, `init`, …). **Keine `anthropic-skills:*`-Einträge** → Befund (4). (`/private/tmp/abs123-probe1b-baseline-skills.json`)

### P2a — Echter Seam-Spawn mit `qas.md`
```bash
printf '…Liste TOOLS und SKILLS…' | ORCH_MODEL=claude-haiku-4-5-20251001 ORCH_MAX_TURNS=2 \
  scripts/orchestrator-spawn-claude.sh qas ABS-123 /private/tmp/abs123-packet.txt
```
```
"result": "TOOLS:\n- Read\n- Bash\n\nSKILLS: KEIN SKILL-TOOL"
```
→ Seat sieht nur die Frontmatter-Tools; **kein Skill-Tool**. (`/private/tmp/abs123-probe2a-qas-seat.json`)

### P2b — Seam-Spawn mit `Skill` in tools: (Testkopie, nicht Repo-Datei)
```bash
# /private/tmp/abs123-agents/qas-skilltest.md = qas.md mit
#   name: qas-skilltest / tools: [Read, Bash, Grep, Skill]
printf '…' | ORCH_AGENTS_DIR=/private/tmp/abs123-agents ORCH_MODEL=claude-haiku-4-5-20251001 ORCH_MAX_TURNS=2 \
  scripts/orchestrator-spawn-claude.sh qas-skilltest ABS-123 /private/tmp/abs123-packet2.txt
```
```
"result": "TOOLS:\n- Read\n- Bash\n- Skill\n\nSKILLS:\n- jira-sop\n- git-advanced\n- code-review\n- verify\n… (voller 62er-Katalog)"
```
(`/private/tmp/abs123-probe2b-qas-skill.json`)

### P3a — Invocation Repo-Skill `jira-sop` unter Seam-Flags: **DENIED**
```bash
printf 'Rufe über das Skill-Tool den Skill "jira-sop" auf…' | ORCH_AGENTS_DIR=/private/tmp/abs123-agents \
  ORCH_MODEL=claude-haiku-4-5-20251001 ORCH_MAX_TURNS=4 scripts/orchestrator-spawn-claude.sh qas-skilltest …
```
```json
"permission_denials": [{"tool_name": "Skill", "tool_input": {"skill": "jira-sop"}}]
"result": "Ich kann das Skill-Tool nicht aufrufen, da Claude Code aktuell im \"don't ask mode\" läuft und die Skill-Nutzung blockiert ist. …"
```
(`/private/tmp/abs123-probe3a-jira-sop.json`)

### P3b — Invocation CLI-Built-in `verify` unter Seam-Flags: **OK**
```bash
printf 'Rufe über das Skill-Tool den Skill "verify" auf und gib die erste Überschrift zurück…' | … scripts/orchestrator-spawn-claude.sh qas-skilltest …
```
```json
"num_turns": 3, "result": "**Verification is runtime observation.**"
```
→ Built-in-Skill wurde real geladen und die erste Instruktionszeile wörtlich zurückgegeben. (`/private/tmp/abs123-probe3b-verify.json`)

### P3c — `jira-sop` mit `--allowedTools "Skill"`: **OK**
```bash
claude -p --agents "$AGENTS_JSON" --agent qas-skilltest --max-turns 4 \
  --permission-mode dontAsk --allowedTools "Skill" --output-format json --model claude-haiku-4-5-20251001
```
```json
"num_turns": 3, "permission_denials": [], "result": "# Jira SOP Skill (Atlassian MCP)"
```
→ Exakt die erste Überschrift von `.claude/skills/jira-sop/SKILL.md`; Repo-Skill real ausgeführt. (`/private/tmp/abs123-probe3c-allowedtools.json`)

### P5 — Enforcement-Check (Allowlist ist hart)
```bash
printf 'Versuche mit dem Write-Tool /private/tmp/abs123-write-test.txt zu erstellen; und rufe das Skill-Tool auf…' | \
  ORCH_MODEL=claude-haiku-4-5-20251001 ORCH_MAX_TURNS=3 scripts/orchestrator-spawn-claude.sh qas …
```
```
"result": "WRITE-TOOL NICHT VERFÜGBAR\n\nSKILL-TOOL NICHT VERFÜGBAR"
ls: /private/tmp/abs123-write-test.txt: No such file or directory
```
(`/private/tmp/abs123-probe5-enforcement.json`)

---

## (d) Empfehlung

**Plan A (Verdrahtung über `tools:`-Erweiterung) funktioniert — aber nur zusammen mit einer Permission-Freigabe.** Konkret zwei Bausteine:

1. **Pro Rolle `Skill` in die `tools:`-Frontmatter aufnehmen** (macht Tool + Katalog sichtbar; Probe P2b). Ohne diesen Eintrag ist die Allowlist hart und nichts geht (P2a/P5).
2. **Skill-Invocation für Nicht-Built-ins freischalten**, da `--permission-mode dontAsk` Repo-/User-Skills still verweigert (P3a). Zwei verifizierbare Wege:
   - Seam-Erweiterung: `--allowedTools "Skill"` im Spawn-Skript mitgeben (verifiziert, P3c) — idealerweise als opt-in Env-Seam (`ORCH_ALLOW_SKILLS=1`) und/oder granular pro Rolle (`Skill(jira-sop)`-Syntax wäre zu verifizieren, bevor man sich darauf stützt);
   - alternativ eine `permissions.allow: ["Skill"]`-Regel in einer echten `.claude/settings.json` (das Repo hat heute nur `settings.template.json` — nicht getestet, da es eine Repo-Änderung wäre).

**Plan B (Repo-Spiegelung von Built-in-Skill-Inhalten) ist NICHT nötig** für die Erreichbarkeit: CLI-Built-ins (`verify`, `code-review`, …) und Repo-Skills sind headless voll vorhanden bzw. ausführbar. Einzige Ausnahme, für die eine Spiegelung/Alternative nötig wäre: **`anthropic-skills:*` (docx/pdf/pptx/xlsx)** existieren in der CLI-Headless-Welt nicht (P1b) — falls Seats diese Fähigkeiten brauchen, sind sie separat zu lösen (eigene Repo-Skills oder Verzicht).

**Offene Punkte für das Verdrahtungs-Ticket:**
- Granularität `Skill(<name>)` in `--allowedTools`/settings verifizieren (Least-Privilege statt Pauschal-`Skill`).
- Sicherheitsabwägung: `Skill` gibt den GESAMTEN Katalog frei, inkl. deploy-/release-Commands — für Gate-Rollen (QAS, security-engineer) ggf. nur mit granularer Allow-Regel.
- Resume-Pfad (`ORCH_RESUME_SESSION_ID`, ohne `--agents`): Toolset kommt aus der Ursprungs-Session; Verdrahtung muss beim ERST-Spawn greifen.
- `Grep`-Self-Report-Anomalie (Fußnote ¹) bei Gelegenheit klären; kein Blocker.
