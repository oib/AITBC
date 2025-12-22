# AITBC – Artificial Intelligence Token Blockchain

## Overview (Recovered)

- AITBC couples decentralized blockchain control with asset‑backed value derived from AI computation.
- No pre‑mint: tokens are minted by providers **only after** serving compute; prices are set by providers (can be free at bootstrap).

## Staged Development Roadmap

### Stage 1: Client–Server Prototype (no blockchain, no hub)

- Direct client → server API.
- API‑key auth; local job logging.
- Goal: validate AI service loop and throughput.

### Stage 2: Blockchain Integration

- Introduce **AIToken** and minimal smart contracts for minting + accounting.
- Mint = amount of compute successfully served; no premint.

### Stage 3: AI Pool Hub

- Hub matches requests to multiple servers (sharding/parallelization), verifies outputs, and accounts contributions.
- Distributes payments/minted tokens proportionally to work.

### Stage 4: Marketplace

- Web DEX/market to buy/sell AITokens; price discovery; reputation and SLAs.

## System Architecture: Actors

- **Client** – requests AI jobs (e.g., image/video generation).
- **Server/Provider** – runs models (Stable Diffusion, PyTorch, etc.).
- **Blockchain Node** – ledger + minting rules.
- **AI Pool Hub** – orchestration, metering, payouts.

## Token Minting Logic (Genesis‑less)

- No tokens at boot.
- Provider advertises price/unit (e.g., 1 AIToken per image or per N GPU‑seconds).
- After successful job → provider mints that amount. Free jobs mint 0.

---

# Stage 1 – Technischer Implementierungsplan (Detail)

## Ziele

- Funktionierender End‑to‑End‑Pfad: Prompt → Inferenz → Ergebnis.
- Authentifizierung, Rate‑Limit, Logging.

## Architektur

```
[ Client ]  ⇄  HTTP/JSON  ⇄  [ FastAPI AI‑Server (GPU) ]
```

- Server hostet Inferenz-Endpunkte; Client sendet Aufträge.
- Optional: WebSocket für Streaming‑Logs/Progress.

## Technologie‑Stack

- **Server**: Python 3.10+, FastAPI, Uvicorn, PyTorch, diffusers (Stable Diffusion), PIL.
- **Client**: Python CLI (requests / httpx) oder schlankes Web‑UI.
- **Persistenz**: SQLite oder JSON Log; Artefakte auf Disk/S3‑ähnlich.
- **Sicherheit**: API‑Key (env/secret file), CORS policy, Rate‑Limit (slowapi), timeouts.

## API‑Spezifikation (v0)

### POST `/v1/generate-image`

Request JSON:

```json
{
  "api_key": "<KEY>",
  "prompt": "a futuristic city skyline at night",
  "steps": 30,
  "guidance": 7.5,
  "width": 512,
  "height": 512,
  "seed": 12345
}
```

Response JSON:

```json
{
  "status": "ok",
  "job_id": "2025-09-26-000123",
  "image_base64": "data:image/png;base64,....",
  "duration_ms": 2180,
  "gpu_seconds": 1.9
}
```

### GET `/v1/health`

- Rückgabe von `{ "status": "ok", "gpu": "RTX 2060", "model": "SD1.5" }`.

## Server‑Ablauf (Pseudocode)

```python
@app.post("/v1/generate-image")
def gen(req: Request):
    assert check_api_key(req.api_key)
    rate_limit(req.key)
    t0 = now()
    img = stable_diffusion.generate(prompt=req.prompt, ...)
    log_job(user=req.key, gpu_seconds=measure_gpu(), ok=True)
    return {"status":"ok", "image_base64": b64(img), "duration_ms": ms_since(t0)}
```

## Betriebliche Aspekte

- **Logging**: strukturierte Logs (JSON) inkl. Prompt‑Hash, Laufzeit, GPU‑Sekunden, Exit‑Code.
- **Observability**: Prometheus‑/OpenTelemetry‑Metriken (req/sec, p95 Latenz, VRAM‑Nutzung).
- **Fehler**: Retry‑Policy (idempotent), Graceful shutdown, Max batch/queue size.
- **Sicherheit**: Input‑Sanitization, Upload‑Limits, tmp‑Verzeichnis säubern.

## Setup‑Schritte (Linux, NVIDIA RTX 2060)

```bash
sudo apt update && sudo apt install -y python3-venv git
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn[standard] torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install diffusers transformers accelerate pillow safetensors xformers slowapi httpx
# Start
uvicorn app:app --host 127.0.0.2 --port 8000 --workers 1
```

## Akzeptanzkriterien

- `GET /v1/health` liefert GPU/Model‑Infos.
- `POST /v1/generate-image` liefert innerhalb < 5s ein 512×512 PNG (bei RTX 2060, SD‑1.5, \~30 steps).
- Logs enthalten pro Job mindestens: job\_id, duration\_ms, gpu\_seconds, bytes\_out.

## Nächste Schritte zu Stage 2

- Job‑Quittungsschema definieren (hashbare Receipt für On‑Chain‑Mint später).
- Einheit „Compute‑Einheit“ festlegen (z. B. GPU‑Sekunden, Token/Prompt).
- Nonce/Signatur im Request zur späteren On‑Chain‑Verifikation.

---

## Kurze Stage‑2/3/4‑Vorschau (Implementierungsnotizen)

- **Stage 2 (Blockchain)**: Smart Contract mit `mint(provider, units, receipt_hash)`, Off‑Chain‑Orakel/Attester.
- **Stage 3 (Hub)**: Scheduler (priority, price, reputation), Sharding großer Jobs, Konsistenz‑Checks, Reward‑Split.
- **Stage 4 (Marketplace)**: Orderbook, KYC/Compliance Layer (jurisdictions), Custody‑freie Wallet‑Anbindung.

## Quellen (Auszug)

- Ethereum Smart Contracts: [https://ethereum.org/en/smart-contracts/](https://ethereum.org/en/smart-contracts/)
- PoS Überblick: [https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/](https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/)
- PyTorch Deploy: [https://pytorch.org/tutorials/](https://pytorch.org/tutorials/)
- FastAPI Docs: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)

---

# Stage 1 – Referenz‑Implementierung (Code)

## `.env`

```
API_KEY=CHANGE_ME_SUPERSECRET
MODEL_ID=runwayml/stable-diffusion-v1-5
BIND_HOST=127.0.0.2
BIND_PORT=8000
```

## `requirements.txt`

```
fastapi
uvicorn[standard]
httpx
pydantic
python-dotenv
slowapi
pillow
torch
torchvision
torchaudio
transformers
diffusers
accelerate
safetensors
xformers
```

## `server.py`

```python
import base64, io, os, time, hashlib
from functools import lru_cache
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from PIL import Image

load_dotenv()
API_KEY = os.getenv("API_KEY", "CHANGE_ME_SUPERSECRET")
MODEL_ID = os.getenv("MODEL_ID", "runwayml/stable-diffusion-v1-5")

app = FastAPI(title="AITBC Stage1 Server", version="0.1.0")
limiter = Limiter(key_func=get_remote_address)

class GenRequest(BaseModel):
    api_key: str
    prompt: str
    steps: int = Field(30, ge=5, le=100)
    guidance: float = Field(7.5, ge=0, le=25)
    width: int = Field(512, ge=256, le=1024)
    height: int = Field(512, ge=256, le=1024)
    seed: Optional[int] = None

@lru_cache(maxsize=1)
def load_pipeline():
    from diffusers import StableDiffusionPipeline
    import torch
    pipe = StableDiffusionPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16, safety_checker=None)
    pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
    pipe.enable_attention_slicing()
    return pipe

@app.get("/v1/health")
def health():
    gpu = os.getenv("NVIDIA_VISIBLE_DEVICES", "auto")
    return {"status": "ok", "gpu": gpu, "model": MODEL_ID}

@app.post("/v1/generate-image")
@limiter.limit("10/minute")
def generate(req: GenRequest, request: Request):
    if req.api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api_key")
    t0 = time.time()
    pipe = load_pipeline()
    generator = None
    if req.seed is not None:
        import torch
        generator = torch.Generator(device=pipe.device).manual_seed(int(req.seed))
    result = pipe(req.prompt, num_inference_steps=req.steps, guidance_scale=req.guidance, width=req.width, height=req.height, generator=generator)
    img: Image.Image = result.images[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    dur_ms = int((time.time() - t0) * 1000)
    job_id = hashlib.sha256(f"{t0}-{req.prompt[:64]}".encode()).hexdigest()[:16]
    log_line = {"job_id": job_id, "duration_ms": dur_ms, "bytes_out": len(b64), "prompt_hash": hashlib.sha256(req.prompt.encode()).hexdigest()}
    print(log_line, flush=True)
    return {"status": "ok", "job_id": job_id, "image_base64": f"data:image/png;base64,{b64}", "duration_ms": dur_ms}

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("server:app", host=os.getenv("BIND_HOST", "127.0.0.2"), port=int(os.getenv("BIND_PORT", "8000")), reload=False)
```

## `client.py`

```python
import base64, json, os
import httpx

API = os.getenv("API", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "CHANGE_ME_SUPERSECRET")

payload = {
    "api_key": API_KEY,
    "prompt": "a futuristic city skyline at night, ultra detailed, neon",
    "steps": 30,
    "guidance": 7.5,
    "width": 512,
    "height": 512,
}

r = httpx.post(f"{API}/v1/generate-image", json=payload, timeout=120)
r.raise_for_status()
resp = r.json()
print("job:", resp.get("job_id"), "duration_ms:", resp.get("duration_ms"))
img_b64 = resp["image_base64"].split(",",1)[1]
open("out.png","wb").write(base64.b64decode(img_b64))
print("saved out.png")
```

---

# OpenAPI 3.1 Spezifikation (Stage 1)

```yaml
openapi: 3.1.0
info:
  title: AITBC Stage1 Server
  version: 0.1.0
servers:
  - url: http://localhost:8000
paths:
  /v1/health:
    get:
      summary: Health check
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  status: { type: string }
                  gpu: { type: string }
                  model: { type: string }
  /v1/generate-image:
    post:
      summary: Generate image from text prompt
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [api_key, prompt]
              properties:
                api_key: { type: string }
                prompt: { type: string }
                steps: { type: integer, minimum: 5, maximum: 100, default: 30 }
                guidance: { type: number, minimum: 0, maximum: 25, default: 7.5 }
                width: { type: integer, minimum: 256, maximum: 1024, default: 512 }
                height: { type: integer, minimum: 256, maximum: 1024, default: 512 }
                seed: { type: integer, nullable: true }
      responses:
        '200':
          description: Image generated
          content:
            application/json:
              schema:
                type: object
                properties:
                  status: { type: string }
                  job_id: { type: string }
                  image_base64: { type: string }
                  duration_ms: { type: integer }
```

---

# Stage 2 – Receipt‑/Quittungs‑Schema & Hashing

## JSON Receipt (off‑chain, signierbar)

```json
{
  "job_id": "2025-09-26-000123",
  "provider": "0xProviderAddress",
  "client": "client_public_key_or_id",
  "units": 1.90,
  "unit_type": "gpu_seconds",
  "model": "runwayml/stable-diffusion-v1-5",
  "prompt_hash": "sha256:...",
  "started_at": 1695720000,
  "finished_at": 1695720002,
  "artifact_sha256": "...",
  "nonce": "b7f3...",
  "hub_id": "optional-hub",
  "chain_id": 11155111
}
```

## Hashing

- Kanonische Serialisierung (minified JSON, Felder in alphabetischer Reihenfolge).
- `receipt_hash = keccak256(bytes(serialized))` (für EVM‑Kompatibilität) **oder** `sha256` falls kettenagnostisch.

## Signatur

- Signatur über `receipt_hash`:
  - **secp256k1/ECDSA** (Ethereum‑kompatibel, EIP‑191/EIP‑712) **oder** Ed25519 (falls Off‑Chain‑Attester bevorzugt).
- Felder zur Verifikation on‑chain: `provider`, `units`, `receipt_hash`, `signature`.

## Double‑Mint‑Prevention

- Smart Contract speichert `used[receipt_hash] = true` nach erfolgreichem Mint.

---

# Stage 2 – Smart‑Contract‑Skeleton (Solidity)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Mint {
    function mint(address to, uint256 amount) external;
}

contract AITokenMinter {
    IERC20Mint public token;
    address public attester; // Off‑chain Hub/Oracle, darf Quittungen bescheinigen
    mapping(bytes32 => bool) public usedReceipt; // receipt_hash → consumed

    event Minted(address indexed provider, uint256 units, bytes32 receiptHash);
    event AttesterChanged(address indexed oldA, address indexed newA);

    constructor(address _token, address _attester) {
        token = IERC20Mint(_token);
        attester = _attester;
    }

    function setAttester(address _attester) external /* add access control */ {
        emit AttesterChanged(attester, _attester);
        attester = _attester;
    }

    function mintWithReceipt(
        address provider,
        uint256 units,
        bytes32 receiptHash,
        bytes calldata attesterSig
    ) external {
        require(!usedReceipt[receiptHash], "receipt used");
        // Verify attester signature over EIP‑191 style message: keccak256(abi.encode(provider, units, receiptHash))
        bytes32 msgHash = keccak256(abi.encode(provider, units, receiptHash));
        require(_recover(msgHash, attesterSig) == attester, "bad sig");
        usedReceipt[receiptHash] = true;
        token.mint(provider, units);
        emit Minted(provider, units, receiptHash);
    }

    function _recover(bytes32 msgHash, bytes memory sig) internal pure returns (address) {
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", msgHash));
        (bytes32 r, bytes32 s, uint8 v) = _split(sig);
        return ecrecover(ethHash, v, r, s);
    }

    function _split(bytes memory sig) internal pure returns (bytes32 r, bytes32 s, uint8 v) {
        require(sig.length == 65, "sig len");
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
    }
}
```

> Hinweis: In Produktion Access‑Control (Ownable/Role‑based), Pausable, Reentrancy‑Guard und EIP‑712‑Typed‑Data einführen.

---

# Stage 3 – Hub‑Spezifikation (Kurz)

- **Scheduler**: Round‑robin + Preis/VRAM‑Filter; optional Reputation.
- **Split**: Große Jobs shard‑en; `units` aus Subjobs aggregieren.
- **Verification**: Stichprobenhafte Re‑Auswertung / Konsistenz‑Hashes.
- **Payout**: Proportionale Verteilung; ein Receipt je Gesamtjob.

# Stage 4 – Marketplace (Kurz)

- **Orderbook** (limit/market), **Wallet‑Connect**, Non‑custodial.
- **KYC/Compliance** optional je Jurisdiktion.
- **Reputation/SLAs** on‑/off‑chain verknüpfbar.



---

# Deployment ohne Docker (Bare‑Metal / VM)

## Voraussetzungen

- Ubuntu/Debian mit NVIDIA Treiber (535+) und CUDA/CuDNN passend zur PyTorch‑Version.
- Python 3.10+ und `python3-venv`.
- Öffentliche Ports: **8000/tcp** (API) – optional Reverse‑Proxy auf 80/443.

## Treiber & CUDA (Kurz)

```bash
# NVIDIA Treiber (Beispiel Ubuntu)
sudo apt update && sudo apt install -y nvidia-driver-535
# Nach Reboot: nvidia-smi prüfen
# PyTorch bringt eigenes CUDA-Toolkit über Wheels (empfohlen). Kein System-CUDA zwingend nötig.
```

## Benutzer & Verzeichnisstruktur

```bash
sudo useradd -m -r -s /bin/bash aitbc
sudo -u aitbc mkdir -p /opt/aitbc/app /opt/aitbc/logs
# Code nach /opt/aitbc/app kopieren
```

## Virtualenv & Abhängigkeiten

```bash
sudo -u aitbc bash -lc '
  cd /opt/aitbc/app && python3 -m venv venv && source venv/bin/activate && \
  pip install --upgrade pip && pip install -r requirements.txt 
'
```

## Konfiguration (.env)

```
API_KEY=<GEHEIM>
MODEL_ID=runwayml/stable-diffusion-v1-5
BIND_HOST=127.0.0.1   # hinter Reverse Proxy
BIND_PORT=8000
```

## Systemd‑Unit (Uvicorn)

`/etc/systemd/system/aitbc.service`

```ini
[Unit]
Description=AITBC Stage1 FastAPI Server
After=network-online.target
Wants=network-online.target

[Service]
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc/app
EnvironmentFile=/opt/aitbc/app/.env
ExecStart=/opt/aitbc/app/venv/bin/python -m uvicorn server:app --host ${BIND_HOST} --port ${BIND_PORT} --workers 1
Restart=always
RestartSec=3
# GPU/VRAM limits optional per nvidia-visible-devices
StandardOutput=append:/opt/aitbc/logs/stdout.log
StandardError=append:/opt/aitbc/logs/stderr.log

[Install]
WantedBy=multi-user.target
```

Aktivieren & Starten:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aitbc.service
sudo systemctl status aitbc.service
```

## Reverse Proxy (optional, ohne Docker)

### Nginx (TLS via Certbot)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo tee /etc/nginx/sites-available/aitbc <<'NG'
server {
  listen 80; server_name example.com;
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
NG
sudo ln -s /etc/nginx/sites-available/aitbc /etc/nginx/sites-enabled/aitbc
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d example.com
```

## Firewall/Netzwerk

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Monitoring ohne Docker

- **systemd**: `journalctl -u aitbc -f`
- **Metriken**: Prometheus Node Exporter, `nvtop`/`nvidia-smi dmon` für GPU.
- **Alerts**: systemd `Restart=always`, optional Monit.

## Zero‑Downtime Update (Rolling ohne Container)

```bash
sudo systemctl stop aitbc
sudo -u aitbc bash -lc 'cd /opt/aitbc/app && git pull && source venv/bin/activate && pip install -r requirements.txt'
sudo systemctl start aitbc
```

## Härtung & Best Practices

- Starker API‑Key, IP‑basierte Allow‑List am Reverse‑Proxy.
- Rate‑Limit (slowapi) aktivieren; Request‑Body‑Limits setzen (`client_max_body_size`).
- Temporäre Dateien regelmäßig bereinigen (systemd tmpfiles).
- Separate GPU‑Workstation vs. Edge‑Expose (API hinter Proxy).

> Hinweis: Diese Anleitung vermeidet bewusst jeglichen Docker‑Einsatz und nutzt **systemd + venv** für einen reproduzierbaren, schlanken Betrieb.

