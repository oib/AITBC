# Layout & Frontend Guidelines (Windsurf)

Target: **mobile‑first**, dark theme, max content width **960px** on desktop. Reference device: **Nothing Phone 2a**.

---

## 1) Design System

### 1.1 Color (Dark Theme)
- `--bg-0: #0b0f14` (page background)
- `--bg-1: #11161c` (cards/sections)
- `--tx-0: #e6edf3` (primary text)
- `--tx-1: #a7b3be` (muted)
- `--pri:  #ff7a1a` (accent orange)
- `--ice:  #b9ecff` (ice accent)
- `--ok:   #3ddc97`
- `--warn: #ffcc00`
- `--err:  #ff4d4d`

### 1.2 Typography
- Base font-size: **16px** (mobile), scale up at desktop.
- Font stack: System UI (`-apple-system, Segoe UI, Roboto, Inter, Arial, sans-serif`).
- Line-height: 1.5 body, 1.2 headings.

### 1.3 Spacing (8‑pt grid)
- `--s-1: 4px`, `--s-2: 8px`, `--s-3: 12px`, `--s-4: 16px`, `--s-5: 24px`, `--s-6: 32px`, `--s-7: 48px`, `--s-8: 64px`.

### 1.4 Radius & Shadow
- Radius: `--r-1: 8px`, `--r-2: 16px`.
- Shadow (subtle): `0 4px 20px rgba(0,0,0,.25)`.

---

## 2) Grid & Layout

### 2.1 Container
- **Mobile‑first**: full‑bleed padding.
- Desktop container: **max‑width: 960px**, centered.
- Side gutters: 16px (mobile), 24px (tablet), 32px (desktop).

**Breakpoint summary**
| Token | Min width | Container behaviour | Notes |
| --- | --- | --- | --- |
| `--bp-sm` | 360px | Fluid | Single-column layouts prioritise readability.
| `--bp-md` | 480px | Fluid | Allow two-up cards or media/text pairings when needed.
| `--bp-lg` | 768px | Max-width 90% (capped at 960px) | Stage tablet/landscape experiences before full desktop.
| `--bp-xl` | 960px | Fixed 960px max width | Full desktop grid, persistent side rails allowed.

Always respect `env(safe-area-inset-*)` for notch devices (use helpers like `.safe-b`).

### 2.2 Columns
- 12‑column grid on screens ≥ **960px**.
- Column gutter: 16px (mobile), 24px (≥960px).
- Utility classes (examples):
  - `.row { display:grid; grid-template-columns: repeat(12, 1fr); gap: var(--gutter); }`
  - `.col-12, .col-6, .col-4, .col-3` for common spans on desktop.
  - Mobile stacks by default; use responsive helpers at breakpoints.

### 2.3 Breakpoints (Nothing Phone 2a aware)
- `--bp-sm: 360px` (small phones)
- `--bp-md: 480px` (Nothing 2a width in portrait ~ 412–480 CSS px)
- `--bp-lg: 768px` (tablets / landscape phones)
- `--bp-xl: 960px` (desktop container)

**Mobile layout rules:**
- Navigation collapses to icon buttons with overflow menu at `--bp-sm`.
- Multi-column sections stack; keep vertical rhythm using `var(--s-6)`.
- Sticky headers take 56px height; ensure content uses `.safe-b` for bottom insets.

**Desktop enhancements:**
- Activate `.row` grid with `.col-*` spans at `--bp-xl`.
- Introduce side rail for filters or secondary nav (span 3 or 4 columns).
- Increase typographic scale by 1 step (`clamp` already handles this).

> **Rule:** Build for < `--bp-lg` first; enhance progressively at `--bp-lg` and `--bp-xl`.

---

## 3) Page Chrome

### 3.1 Header
- Sticky top, height 56–64px.
- Left: brand; Right: primary action or menu.
- Translucent on scroll (backdrop‑filter), solid at top.

### 3.2 Footer
- Thin bar; meta links. Uses ice accent for separators.

### 3.3 Main
- Vertical rhythm: sections spaced by `var(--s-7)` (mobile) / `var(--s-8)` (desktop).
- Cards: background `var(--bg-1)`, radius `var(--r-2)`, padding `var(--s-6)`.

---

## 4) CSS File Strategy (per page)

**Every HTML page ships its own CSS file**, plus shared layers:

- `/css/base.css` — resets, variables, typography, utility helpers.
- `/css/components.css` — buttons, inputs, cards, modals, toast.
- `/css/layout.css` — grid/container/header/footer.
- `/css/pages/<page>.css` — page‑specific rules (one per HTML page).

**Naming** (BEM‑ish): `block__elem--mod`. Avoid nesting >2 levels.

**Example includes:**
```html
<link rel="stylesheet" href="/css/base.css">
<link rel="stylesheet" href="/css/components.css">
<link rel="stylesheet" href="/css/layout.css">
<link rel="stylesheet" href="/css/pages/dashboard.css">
```

---

## 5) Utilities (recommended)
- Spacing: `.mt-4`, `.mb-6`, `.px-4`, `.py-6` (map to spacing scale).
- Flex/Grid: `.flex`, `.grid`, `.ai-c`, `.jc-b`.
- Display: `.hide-sm`, `.hide-lg` using media queries.

---

## 6) Toast Messages (center bottom)

**Position:** centered at bottom above safe‑area insets.

**Behavior:**
- Appear for 3–5s; pause on hover; dismiss on click.
- Max width 90% on mobile, 420px desktop.
- Elevation + subtle slide/fade.

**Structure:**
```html
<div id="toast-root" aria-live="polite" aria-atomic="true"></div>
```

**Styles (concept):**
```css
#toast-root { position: fixed; left: 50%; bottom: max(16px, env(safe-area-inset-bottom)); transform: translateX(-50%); z-index: 9999; }
.toast { background: var(--bg-1); color: var(--tx-0); border: 1px solid rgba(185,236,255,.2); padding: var(--s-5) var(--s-6); border-radius: var(--r-2); box-shadow: 0 10px 30px rgba(0,0,0,.35); margin-bottom: var(--s-4); max-width: min(420px, 90vw); }
.toast--ok { border-color: rgba(61,220,151,.35); }
.toast--warn { border-color: rgba(255,204,0,.35); }
.toast--err { border-color: rgba(255,77,77,.35); }
```

**JS API (minimal):**
```js
function showToast(msg, type = "ok", ms = 3500) {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.role = "status";
  el.textContent = msg;
  root.appendChild(el);
  const t = setTimeout(() => el.remove(), ms);
  el.addEventListener("mouseenter", () => clearTimeout(t));
  el.addEventListener("click", () => el.remove());
}
```

---

## 7) Browser Notifications (system tray)

**When to use:** Only for important, user‑initiated events (e.g., a new match, message, or scheduled session start). Always provide an in‑app alternative (toast/modal) for users who deny permission.

**Permission flow:**
```js
async function ensureNotifyPermission() {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const res = await Notification.requestPermission();
  return res === "granted";
}
```

**Send notification:**
```js
function notify(opts) {
  if (Notification.permission !== "granted") return;
  const n = new Notification(opts.title || "Update", {
    body: opts.body || "",
    icon: opts.icon || "/icons/notify.png",
    tag: opts.tag || "app-event",
    requireInteraction: !!opts.sticky
  });
  if (opts.onclick) n.addEventListener("click", opts.onclick);
}
```

**Pattern:**
```js
const ok = await ensureNotifyPermission();
if (ok) notify({ title: "Match window opens soon", body: "Starts in 10 min" });
else showToast("Enable notifications in settings to get alerts", "warn");
```

---

## 8) Forms & Inputs
- Hit target ≥ 44×44px, labels always visible.
- Focus ring: `outline: 2px solid var(--ice)`.
- Validation: inline text in `--warn/--err`; never only color.

---

## 9) Performance
- CSS: ship **only** what a page uses (per‑page CSS). Avoid giant bundles.
- Images: `loading="lazy"`, responsive sizes; WebP/AVIF first.
- Fonts: use system fonts; if custom, `font-display: swap`.

---

## 10) Accessibility
- Ensure color contrast ratios meet WCAG AA standards (e.g., 4.5:1 for text and 3:1 for large text).
- Use semantic HTML elements (<header>, <nav>, <main>, etc.) and ARIA attributes for dynamic content.
- Support keyboard navigation with logical tab order and visible focus indicators.
- Test for screen readers, providing text alternatives for images and ensuring forms are labeled correctly.
- Adapt layouts for assistive technologies using media queries and flexible components.

## 11) Accessibility Integration
- Apply utility classes for focus states (e.g., :focus-visible with visible outline).
- Use ARIA roles for custom widgets and ensure all content is perceivable, operable, understandable, and robust.

## 12) Breakpoint Examples
```css
/* Mobile-first defaults here */
@media (min-width: 768px) { /* tablets / landscape phones */ }
@media (min-width: 960px) { /* desktop grid & container */ }
```

---

## 13) Checklist (per page)
- [ ] Uses `/css/pages/<page>.css` + shared layers
- [ ] Container max‑width 960px, centered; gutters follow breakpoint summary
- [ ] Mobile‑first; tests on Nothing Phone 2a
- [ ] Toasts render center‑bottom
- [ ] Notifications gated by permission & mirrored with toasts
- [ ] A11y pass (headings order, labels, focus, contrast)



---

## Appendix A — `/css/base.css`
```css
/* Base: variables, reset, typography, utilities */
:root{
  --bg-0:#0b0f14; --bg-1:#11161c;
  --tx-0:#e6edf3; --tx-1:#a7b3be;
  --pri:#ff7a1a; --ice:#b9ecff;
  --ok:#3ddc97; --warn:#ffcc00; --err:#ff4d4d;

  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px;
  --s-5:24px; --s-6:32px; --s-7:48px; --s-8:64px;
  --r-1:8px; --r-2:16px;
  --gutter:16px;
}

@media (min-width:960px){ :root{ --gutter:24px; } }

/* Reset */
*{ box-sizing:border-box; }
html,body{ height:100%; }
html{ color-scheme:dark; }
body{
  margin:0; background:var(--bg-0); color:var(--tx-0);
  font:16px/1.5 -apple-system, Segoe UI, Roboto, Inter, Arial, sans-serif;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
img,svg,video{ max-width:100%; height:auto; display:block; }
button,input,select,textarea{ font:inherit; color:inherit; }
:focus-visible{ outline:2px solid var(--ice); outline-offset:2px; }

/* Typography */
h1{ font-size:clamp(24px, 3.5vw, 36px); line-height:1.2; margin:0 0 var(--s-4); }
h2{ font-size:clamp(20px, 3vw, 28px); line-height:1.25; margin:0 0 var(--s-3); }
h3{ font-size:clamp(18px, 2.5vw, 22px); line-height:1.3; margin:0 0 var(--s-2); }
p{ margin:0 0 var(--s-4); color:var(--tx-1); }

/* Links */
a{ color:var(--ice); text-decoration:none; }
a:hover{ text-decoration:underline; }

/* Utilities */
.container{ width:100%; max-width:960px; margin:0 auto; padding:0 var(--gutter); }
.flex{ display:flex; } .grid{ display:grid; }
.ai-c{ align-items:center; } .jc-b{ justify-content:space-between; }
.mt-4{ margin-top:var(--s-4);} .mb-6{ margin-bottom:var(--s-6);} .px-4{ padding-left:var(--s-4); padding-right:var(--s-4);} .py-6{ padding-top:var(--s-6); padding-bottom:var(--s-6);} 
.hide-sm{ display:none; }
@media (min-width:960px){ .hide-lg{ display:none; } .hide-sm{ display:initial; } }

/* Safe area helpers */
.safe-b{ padding-bottom:max(var(--s-4), env(safe-area-inset-bottom)); }
```

---

## Appendix B — `/css/layout.css`
```css
/* Grid, header, footer, sections */
.row{ display:grid; grid-template-columns:repeat(12, 1fr); gap:var(--gutter); }

/* Mobile-first: stack columns */
[class^="col-"]{ grid-column:1/-1; }

@media (min-width:960px){
  .col-12{ grid-column:span 12; }
  .col-6{ grid-column:span 6; }
  .col-4{ grid-column:span 4; }
  .col-3{ grid-column:span 3; }
}

header.site{
  position:sticky; top:0; z-index:50;
  backdrop-filter:saturate(1.2) blur(8px);
  background:color-mix(in oklab, var(--bg-0) 85%, transparent);
  border-bottom:1px solid rgba(185,236,255,.12);
}
header.site .inner{ height:64px; }

footer.site{
  margin-top:var(--s-8);
  border-top:1px solid rgba(185,236,255,.12);
  background:var(--bg-0);
}
footer.site .inner{ height:56px; font-size:14px; color:var(--tx-1); }

main section{ margin: var(--s-7) 0; }
.card{
  background:var(--bg-1);
  border:1px solid rgba(185,236,255,.12);
  border-radius:var(--r-2);
  padding:var(--s-6);
  box-shadow:0 4px 20px rgba(0,0,0,.25);
}
```

---

## Appendix C — `/css/components.css`
```css
/* Buttons */
.btn{ display:inline-flex; align-items:center; justify-content:center; gap:8px;
  border-radius:var(--r-1); padding:10px 16px; border:1px solid transparent; cursor:pointer;
  background:var(--pri); color:#111; font-weight:600; text-align:center; }
.btn:hover{ filter:brightness(1.05); }
.btn--subtle{ background:transparent; color:var(--tx-0); border-color:rgba(185,236,255,.2); }
.btn--ghost{ background:transparent; color:var(--pri); border-color:transparent; }
.btn:disabled{ opacity:.6; cursor:not-allowed; }

/* Inputs */
.input{ width:100%; background:#0e1319; color:var(--tx-0);
  border:1px solid rgba(185,236,255,.18); border-radius:var(--r-1);
  padding:12px 14px; }
.input::placeholder{ color:#6f7b86; }

/* Badges */
.badge{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; border:1px solid rgba(185,236,255,.2); }
.badge--ok{ color:#0c2; border-color:rgba(61,220,151,.4); }
.badge--warn{ color:#fc0; border-color:rgba(255,204,0,.4); }
.badge--err{ color:#f66; border-color:rgba(255,77,77,.4); }

/* Toasts */
#toast-root{ position:fixed; left:50%; bottom:max(16px, env(safe-area-inset-bottom)); transform:translateX(-50%); z-index:9999; }
.toast{ background:var(--bg-1); color:var(--tx-0);
  border:1px solid rgba(185,236,255,.2); padding:var(--s-5) var(--s-6);
  border-radius:var(--r-2); box-shadow:0 10px 30px rgba(0,0,0,.35);
  margin-bottom:var(--s-4); max-width:min(420px, 90vw);
  opacity:0; translate:0 8px; animation:toast-in .24s ease-out forwards; }
.toast--ok{ border-color:rgba(61,220,151,.35); }
.toast--warn{ border-color:rgba(255,204,0,.35); }
.toast--err{ border-color:rgba(255,77,77,.35); }
@keyframes toast-in{ to{ opacity:1; translate:0 0; } }
```



---

## Appendix D — `/js/toast.js`
```js
export function showToast(msg, type = "ok", ms = 3500) {
  const root = document.getElementById("toast-root") || (() => {
    const r = document.createElement("div");
    r.id = "toast-root";
    document.body.appendChild(r);
    return r;
  })();

  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.role = "status";
  el.textContent = msg;
  root.appendChild(el);

  const t = setTimeout(() => el.remove(), ms);
  el.addEventListener("mouseenter", () => clearTimeout(t));
  el.addEventListener("click", () => el.remove());
}
```

---

## Appendix E — `/js/notify.js`
```js
export async function ensureNotifyPermission() {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const res = await Notification.requestPermission();
  return res === "granted";
}

export function notify(opts) {
  if (Notification.permission !== "granted") return;
  const n = new Notification(opts.title || "Update", {
    body: opts.body || "",
    icon: opts.icon || "/icons/notify.png",
    tag: opts.tag || "app-event",
    requireInteraction: !!opts.sticky
  });
  if (opts.onclick) n.addEventListener("click", opts.onclick);
}
```



---

## Appendix F — `/css/pages/dashboard.css`
```css
/* Dashboard specific styles */
.dashboard-header{
  margin-bottom:var(--s-6);
  display:flex; align-items:center; justify-content:space-between;
}
.dashboard-header h1{ font-size:28px; color:var(--pri); }

.stats-grid{
  display:grid;
  gap:var(--s-5);
  grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));
}
.stat-card{
  background:var(--bg-1);
  border:1px solid rgba(185,236,255,.12);
  border-radius:var(--r-2);
  padding:var(--s-5);
  text-align:center;
}
.stat-card h2{ margin:0; font-size:20px; color:var(--ice); }
.stat-card p{ margin:var(--s-2) 0 0; color:var(--tx-1); font-size:14px; }

.activity-feed{
  margin-top:var(--s-7);
}
.activity-item{
  border-bottom:1px solid rgba(185,236,255,.1);
  padding:var(--s-4) 0;
  display:flex; align-items:center; gap:var(--s-4);
}
.activity-item:last-child{ border-bottom:none; }
.activity-icon{ width:32px; height:32px; border-radius:50%; background:var(--pri); display:flex; align-items:center; justify-content:center; color:#111; font-size:16px; }
.activity-text{ flex:1; font-size:14px; color:var(--tx-0); }
.activity-time{ font-size:12px; color:var(--tx-1); }
