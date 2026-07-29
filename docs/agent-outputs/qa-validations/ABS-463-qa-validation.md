# QA Validation Report — ABS-463

**Ticket**: ABS-463 — Item drawer: content first, rendered markdown, history above actions  
**Branch**: ABS-463-auto  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`  
**QAS run date**: 2026-07-19  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Drawer shows rendered markdown (headings/lists/bold visible); raw `##` never visible | ✅ PASS | Unit tests (4 markdown tests) + e2e: `body.getByRole("heading", { name: "Goal" })` visible; `body NOT.toContainText("## Goal")` |
| AC2 | Body and timeline visible without scrolling past action forms at 1280×720 viewport | ✅ PASS | TicketDrawer reordered: meta → rendered body → timeline → Actions last; e2e asserts `bodyBox.y < actionsBox.y` |
| AC3 | XSS test: body containing `<script>` renders inert | ✅ PASS | Parser never emits HTML nodes; `<script>alert(1)</script>` → plain text token; verified by unit test + manual spot-check |
| AC4 | Existing drawer e2e (seat-drawer, useDrawerURL/ABS-420 hash behavior) stays green | ✅ PASS | seat-drawer.spec.ts: 9/9 passed; filters.spec.ts (useDrawerURL): included in full suite 60/61 |

---

## Test Run Evidence (ABS-453 Green-Run Proof)

### Unit Tests — `test/markdown.test.ts` (new file, changed by this commit)

**Command**: `node --import tsx --test --test-concurrency=1 "test/markdown.test.ts"`  
**Result**: **4 passed, 0 failed**  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`

```
✔ ABS-463: headings, lists and bold parse into structural blocks (0.784ms)
✔ ABS-463: bold and inline code parse to typed inline tokens (0.602ms)
✔ ABS-463: fenced code blocks are captured raw, not inline-parsed (0.055ms)
✔ ABS-463 (XSS): <script> in the body is kept as inert text, not an HTML node (0.086ms)
ℹ tests 4
ℹ pass 4
ℹ fail 0
```

### Unit Tests — Full Web Suite

**Command**: `node --import tsx --test --test-concurrency=1 "test/**/*.test.ts"`  
**Result**: **17 passed, 0 failed**  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`

### E2E Tests — `e2e/board.spec.ts` (changed by this commit — ABS-463 assertions)

**Command**: `DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic npx playwright test e2e/board.spec.ts --reporter=line`  
**Result**: **2 passed, 0 failed**  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`

```
[1/2] e2e/board.spec.ts:39:1 › login → board → live update → detail drawer
[2/2] e2e/board.spec.ts:88:1 › S9 (ABS-241): human transition + release toggle from the drawer, orchestrator sees it next poll
  2 passed (2.8s)
```

### E2E Tests — `e2e/seat-drawer.spec.ts` (AC4: existing drawer must stay green)

**Command**: `DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic npx playwright test e2e/seat-drawer.spec.ts --reporter=line`  
**Result**: **9 passed, 0 failed**  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`

### E2E Tests — Full Suite

**Command**: `DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic npx playwright test --reporter=line`  
**Result**: **60 passed, 1 skipped (pre-existing), 0 failed**  
**Commit**: `6d095a09d75fc40f1cea8d71c9ed663c62413044`

---

## Gate Checks

| Check | Result |
|-------|--------|
| TypeScript typecheck (`tsc --noEmit`) | ✅ PASS (exit 0) |
| ESLint (changed files) | ✅ PASS (exit 0, CSS excluded by config — expected) |
| Unit tests (17 total, 4 new ABS-463) | ✅ PASS |
| E2E full suite | ✅ PASS (60/61, 1 pre-existing skip) |

---

## Security Spot-Check (AC3 — XSS)

Manual verification run against the parser:
```
Input: '<script>alert(1)</script>'
Block type: paragraph
Text value: <script>alert(1)</script>
XSS inert: true
```

- No `dangerouslySetInnerHTML` anywhere in Markdown.tsx or TicketDrawer.tsx (verified via code review)
- Parser produces only `text | bold | code` inline token types — no `html` node type exists
- Heading tag computed as `h${Math.min(level+2, 6)}` from numeric level only — no arbitrary tag injection
- Fenced code captured as raw text, never inline-parsed

---

## Code Review Notes

- **`src/markdown.ts`** (~114 lines): minimal in-tree parser, no new dependency. Architect signed off. Guards `null`/`undefined` src with `src ?? ""`.
- **`src/components/Markdown.tsx`**: React renderer via children only, no `dangerouslySetInnerHTML`. `data-testid="drawer-body"` for e2e targeting.
- **`src/components/TicketDrawer.tsx`**: Reordered to meta → `<Markdown>` body → timeline → `<Actions>` (moved last). Clear `data-testid="drawer-content"` and `data-testid="actions"` for layout assertions.
- **`src/util.ts`**: `humanizeTimestamp()` guards null/undefined/NaN, returns relative text with absolute ISO on hover (`title` attribute). Reuses `formatAge()`.
- **`src/styles.css`**: `.md-body`, `.md-code`, `.md-inline-code` styling added. No global resets.

---

## Verdict

**✅ APPROVED**  
All 4 ACs met. Green-run proof collected personally (ABS-453 satisfied). No blocking findings.  
Exit: Story Acceptance (no `design` flag on ticket).
