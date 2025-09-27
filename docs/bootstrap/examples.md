# examples/ — Minimal runnable examples for integrators

This folder contains three self-contained, copy-pasteable starters that demonstrate how to talk to the coordinator API, submit jobs, poll status, and (optionally) verify signed receipts.

```
examples/
├─ explorer-webexplorer-web/    # (docs live elsewhere; not a runnable example)
├─ quickstart-client-python/    # Minimal Python client
├─ quickstart-client-js/        # Minimal Node/Browser client
└─ receipts-sign-verify/        # Receipt format + sign/verify demos
```

> Conventions: Debian 12/13, zsh, no sudo, run as root if you like. Keep env in a `.env` file. Replace example URLs/tokens with your own.

---

## 1) quickstart-client-python/

### What this shows
- Create a job request
- Submit to `COORDINATOR_URL`
- Poll job status until `succeeded|failed|timeout`
- Fetch the result payload
- (Optional) Save the receipt JSON for later verification

### Files Windsurf should ensure exist
- `main.py` — the tiny client (≈ 80–120 LOC)
- `requirements.txt` — `httpx`, `python-dotenv` (and `pydantic` if you want models)
- `.env.example` — `COORDINATOR_URL`, `API_TOKEN`
- `README.md` — one-screen run guide

### How to run
```sh
cd examples/quickstart-client-python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Prepare environment
cp .env.example .env
# edit .env → set COORDINATOR_URL=https://api.local.test:8443, API_TOKEN=xyz

# Run
python main.py --prompt "hello compute" --timeout 60

# Outputs:
# - logs to stdout
# - writes ./out/result.json
# - writes ./out/receipt.json (if provided by the coordinator)
```

### Coordinator endpoints the code should touch
- `POST /v1/jobs` → returns `{ job_id }`
- `GET  /v1/jobs/{job_id}` → returns `{ status, progress?, result? }`
- `GET  /v1/jobs/{job_id}/receipt` → returns `{ receipt }` (optional)

Keep the client resilient: exponential backoff (100ms → 2s), total wall-time cap from `--timeout`.

---

## 2) quickstart-client-js/

### What this shows
- Identical flow to the Python quickstart
- Two variants: Node (fetch via `undici`) and Browser (native `fetch`)

### Files Windsurf should ensure exist
- `node/`
  - `package.json` — `undici`, `dotenv`
  - `index.js` — Node example client
  - `.env.example`
  - `README.md`
- `browser/`
  - `index.html` — minimal UI with a Prompt box + “Run” button
  - `app.js` — client logic (no build step)
  - `README.md`

### How to run (Node)
```sh
cd examples/quickstart-client-js/node
npm i
cp .env.example .env
# edit .env → set COORDINATOR_URL, API_TOKEN
node index.js "hello compute"
```

### How to run (Browser)
```sh
cd examples/quickstart-client-js/browser
# Serve statically (choose one)
python3 -m http.server 8080
# or
busybox httpd -f -p 8080
```
Open `http://localhost:8080` and paste your coordinator URL + token in the form.
The app:
- `POST /v1/jobs`
- polls `GET /v1/jobs/{id}` every 1s (with a 60s guard)
- downloads `receipt.json` if available

---

## 3) receipts-sign-verify/

### What this shows
- Receipt JSON structure used by AITBC examples
- Deterministic signing over a canonicalized JSON (RFC 8785-style or stable key order)
- Ed25519 signing & verifying in Python and JS
- CLI snippets to verify receipts offline

> If the project standardizes on another curve, swap the libs accordingly. For Ed25519:
> - Python: `pynacl`
> - JS: `@noble/ed25519`

### Files Windsurf should ensure exist
- `spec.md` — human-readable schema (see below)
- `python/`
  - `verify.py` — `python verify.py ./samples/receipt.json ./pubkeys/poolhub_ed25519.pub`
  - `requirements.txt` — `pynacl`
- `js/`
  - `verify.mjs` — `node js/verify.mjs ./samples/receipt.json ./pubkeys/poolhub_ed25519.pub`
  - `package.json` — `@noble/ed25519`
- `samples/receipt.json` — realistic sample
- `pubkeys/poolhub_ed25519.pub` — PEM or raw 32-byte hex

### Minimal receipt schema (for `spec.md`)
```jsonc
{
  "version": "1",
  "job_id": "string",
  "client_id": "string",
  "miner_id": "string",
  "started_at": "2025-09-26T14:00:00Z",
  "completed_at": "2025-09-26T14:00:07Z",
  "units_billed": 123,             // e.g., “AIToken compute units”
  "result_hash": "sha256:…",       // hex
  "metadata": { "model": "…" },    // optional, stable ordering for signing
  "signature": {
    "alg": "Ed25519",
    "key_id": "poolhub-ed25519-2025-09",
    "sig": "base64url…"            // signature over canonicalized receipt WITHOUT this signature object
  }
}
```

### CLI usage

**Python**
```sh
cd examples/receipts-sign-verify/python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python verify.py ../samples/receipt.json ../pubkeys/poolhub_ed25519.pub
# exit code 0 = valid, non-zero = invalid
```

**Node**
```sh
cd examples/receipts-sign-verify/js
npm i
node verify.mjs ../samples/receipt.json ../pubkeys/poolhub_ed25519.pub
```

**Implementation notes for Windsurf**
- Canonicalize JSON before hashing/signing (stable key order, UTF-8, no trailing spaces).
- Sign bytes of `sha256(canonical_json_without_signature_block)`.
- Reject if `completed_at < started_at`, unknown `alg`, or mismatched `result_hash`.

---

## Shared environment

All quickstarts read the following from `.env` or in-page form fields:

```
COORDINATOR_URL=https://api.local.test:8443
API_TOKEN=replace-me
# Optional: REQUEST_TIMEOUT_SEC=60
```

HTTP headers to include:
```
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

---

## Windsurf checklist (do this automatically)

1. **Create folders & files**
   - `quickstart-client-python/{main.py,requirements.txt,.env.example,README.md}`
   - `quickstart-client-js/node/{index.js,package.json,.env.example,README.md}`
   - `quickstart-client-js/browser/{index.html,app.js,README.md}`
   - `receipts-sign-verify/{spec.md,samples/receipt.json,pubkeys/poolhub_ed25519.pub}`
   - `receipts-sign-verify/python/{verify.py,requirements.txt}`
   - `receipts-sign-verify/js/{verify.mjs,package.json}`

2. **Fill templates**
   - Implement `POST /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/receipt` calls.
   - Poll with backoff; stop at terminal states; write `out/result.json` & `out/receipt.json`.

3. **Wire Ed25519 libs**
   - Python: `pynacl` verify(`public_key`, `message`, `signature`)
   - JS: `@noble/ed25519` verifySync

4. **Add DX niceties**
   - `.env.example` everywhere
   - `README.md` with copy-paste run steps (no global installs)
   - Minimal logging and clear non-zero exit on failure

5. **Smoke tests**
   - Python quickstart runs end-to-end with a mock coordinator (use our tiny FastAPI mock if available).
   - JS Node client runs with `.env`.
   - Browser client works via `http://localhost:8080`.

---

## Troubleshooting

- **401 Unauthorized** → check `API_TOKEN`, CORS (browser), or missing `Authorization` header.
- **CORS in browser** → coordinator must set:
  - `Access-Control-Allow-Origin: *` (or your host)
  - `Access-Control-Allow-Headers: Authorization, Content-Type`
  - `Access-Control-Allow-Methods: GET, POST, OPTIONS`
- **Receipt verify fails** → most often due to non-canonical JSON or wrong public key.

---

## License & reuse

Keep examples MIT-licensed. Add a short header to each file:
```
MIT © AITBC Examples — This is demo code; use at your own risk.
```

