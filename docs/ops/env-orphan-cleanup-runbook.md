# Orphan `/etc/aitbc` env files — cleanup runbook

Issue: #1549 (ENV-ORPHAN-1, BACKUP/AUDIT batch). Scope: **operator-run live
cleanup** — nothing in this document has been executed; every `/etc/aitbc`
deletion is an operator action.

## Verified facts (audit, 10 Nov)

- ~15 env files fleet-wide configure services that have **no systemd unit
  anywhere** — verified by `grep -rln` unit references plus
  `systemctl list-unit-files`/`list-units` on all five hosts.
- **No repo provisioning recreates them.** `scripts/deployment/setup.sh`
  only manages `blockchain.env`, `node.env`, `redis.env` and service env
  files for deployed units; nothing in `scripts/`, `apps/*/`, or
  `examples/` writes `aitbc-hermes-agent.env`, `cache.env`, etc. The
  orphans are residue from manual/older provisioning — deleting them is
  permanent-safe once the pre-checks below pass.
- The repo **ships units that are not deployed** fleet-wide
  (ai-engine ×4, edge, ffmpeg, gpu, hermes-agent, ipfs non-island, miner,
  whisper). Deploy-vs-retire is a product decision — see §4; this
  runbook does not retire units.
- The workspace fleet table (`AGENTS.md`) was already corrected to list
  the units actually running on node1/node2 (no
  Hermes/FFmpeg/Whisper/GPU-miner/marketplace claims).

## 1. Orphan env inventory

| env file(s) | hosts | notes |
|---|---|---|
| `cache.env` (8 keys) | node2 | no unit refs it; 0 repo hits for `CACHE_*` |
| `security.env` (13 keys) | node2 | api-gateway uses `API_GATEWAY_*` names instead |
| `aitbc-edge.env` | node1, node2 | no `aitbc-edge.service` anywhere |
| `aitbc-miner.env` | node0, node2 | inconsistent key names (`MINER_API_KEY` vs `MINER_AUTH_TOKEN`) |
| `aitbc-hermes-agent.env`, `aitbc-ffmpeg.env`, `aitbc-whisper.env`, gpu env | node2 (+node0) | contradicts the old fleet table — no such units exist |
| `aitbc-marketplace.env` | all 5 | no marketplace service; duplicates `aitbc-market.env` |
| `aitbc-market.env` | node0, node1, node2 | `aitbc-market.service` enabled only on hub |
| `aitbc-pool-hub.env` | node0, node2 | `aitbc-pool-hub.service` only on hub + hub1 |
| `aitbc-agent-coordinator.env`, `aitbc-api-gateway.env`, `aitbc-coordinator-api*.env` | hub1 | none of those services run on hub1 (`COIN_REQUEST_AUTO_BUDGET_PER_HOUR=0` deliberately inert) |
| `aitbc-blockchain-p2p.env` | hub1, node0, node1, node2 | `aitbc-blockchain-p2p.service` only on hub |
| `aitbc-exchange.env` (aitbc- prefixed) | node0, node1, node2, hub1 | `aitbc-exchange.service` only on hub — note `exchange.env` (no prefix) IS live: `aitbc-wallet` loads it; do not confuse the two |

## 2. Pre-cleanup verification (per host, per file)

Quarantine is only safe after proving nothing consumes the file:

```bash
# 1. No unit references the env file
sudo grep -rl "EnvironmentFile=.*<name>" /etc/systemd/system/ || true
systemctl list-units 'aitbc-*' --all | grep -i <service> || true

# 2. No drop-in or script sources it
grep -rln "<name>" /etc/systemd/system/ /etc/aitbc/ 2>/dev/null | grep -v "^/etc/aitbc/<name>$" || true

# 3. If a same-named service exists but is disabled, confirm it stays disabled:
systemctl is-enabled <unit>   # expect: disabled / not-found
```

Any hit → stop, the file is not an orphan; investigate instead.

## 3. Cleanup procedure (quarantine, not delete)

Per host, as root:

```bash
Q=/root/etc-aitbc-orphan-quarantine-$(date +%Y%m%d)
install -d -m 0700 "$Q"
# move each verified orphan, preserving the name
mv /etc/aitbc/<orphan>.env "$Q/"
# record what moved
ls -la "$Q" | tee "$Q/MANIFEST.txt"
```

- Keep the quarantine dir ≥30 days (covers a full backup retention
  window); the nightly `aitbc-backup` `/etc/aitbc` leg will pick the
  quarantined copies up only while they remain under `/etc/aitbc` — after
  the move they are outside backup coverage, so delete the quarantine dir
  only after the window or copy it somewhere durable first.
- **Do not delete `exchange.env`** (unprefixed) anywhere — it is live for
  `aitbc-wallet`.
- After cleanup, re-run the §2 checks once more before removing the
  quarantine dir.

## 4. Repo-shipped units never deployed — decision needed

These `.service` files exist in the repo but have no installed unit on
any fleet host (verified 10 Nov). Retiring them is a repo change; deploying
them is an ops change. Director decision per row:

| unit(s) | repo path | note |
|---|---|---|
| `aitbc-ai`, `aitbc-learning`, `aitbc-modality-optimization`, `aitbc-multimodal` | `apps/ai-engine/` | ai-engine stack never deployed |
| `aitbc-edge` | `apps/edge/` | edge compute service never deployed |
| `aitbc-ffmpeg`, `aitbc-whisper` | `apps/ffmpeg/`, `apps/whisper/` | media pipeline never deployed |
| `aitbc-gpu` | `apps/gpu/` | gpu service never deployed |
| `aitbc-hermes-agent` | `apps/hermes_agent/` | agent runtime never deployed |
| `aitbc-ipfs` (non-island) | `apps/ipfs/` | only `aitbc-island-ipfs` runs (node1/node2) |
| `aitbc-miner` | `apps/miner/` | miner never deployed |

Until a retire decision lands, the units stay in the repo — they are
inert without installation and their env files are the orphans listed
above.

## 5. What this runbook does NOT do

- No live `/etc/aitbc` deletions (operator action, §3).
- No unit installs/removals.
- No env value changes — the suspicious-value review is #1548
  (ENV-DRIFT-1), a separate row.
