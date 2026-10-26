# Market CLI Options

**Level**: Advanced
**Prerequisites**: Scenario 07 AI Job Submission, Scenario 75 Market Escrow & Jobs Options
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Market CLI Options

---

## Scenario Overview

> **Option-coverage scenario (MARKET-OPTS-1).** This play walks the
> previously unexercised `aitbc market` options — the largest option
> family in the census (165 options). Read-only queries run live;
> every command that would sign a transaction or move funds stops at a
> free refusal: wallet-not-found, unknown offer/job (offer-resolution
> abort or node-side 4xx), a bogus energy-quote file, or `n` at the
> confirmation prompt. Nothing is signed by a real wallet, nothing is
> spent, and no market record is created.
>
> Played on node0 (checkout `23665e09a`) against the live hub market on
> `hub.aitbc.bubuit.net`; the node's real chain id is `bc-2`.

### What You'll Learn

- Which `aitbc market` queries are free read-only calls
- Where each mutating command refuses when given a throwaway identity
- How the software-offer commands (`run`, `hermes`, `transcribe`,
  `process`, `host`) all share the same offer-resolution refusal
- How the protected GPU rental rail (`gpu quote`/`buy`/`refund`/
  `release`/`status`) refuses before any escrow is touched

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A node that can reach the hub market endpoints
- Two fixture files and one fixture quote used below:

```bash
printf 'x' > /tmp/mo1.mp4
printf 'x' > /tmp/mo1.mp3
cat > /tmp/mo1-quote.json <<'Q'
{"energy_quote":{"version":1,"domain":"aitbc-energy-quote","chain_id":"bc-2","settlement_asset":"AIT","settlement_unit_scale":100000000,"buyer":"0x0000000000000000000000000000000000000001","provider":"0x0000000000000000000000000000000000000002","job_id":"job-mo1","quote_id":"q-mo1","settlement_route":"native","resource_id":"gpu-mo1","model_id":"m","gpu_count":1,"duration_seconds":3600,"eur_per_kwh_scaled":1000000,"tbp_watts":100,"ait_per_eur_scaled":1000000,"rate_version":1,"rate_observed_at":1,"rate_submitted_at":1,"rate_source_kind":"oracle","profile_revision":1,"expires_at":99999999999,"issued_at":1}}
Q
```

---

## Steps

### Step 1: Offer listing filters and renderers (ok)

`market list` filter flags ride on a live read:

```bash
aitbc market list --provider 0x0000000000000000000000000000000000000001 --status active --sort price
```

**Expected output:** an empty `Hardware+Software Bundle Offers` table
(exit 0 — no offers from that provider).

`--mine` resolves the local wallet/node identity and filters:

```bash
aitbc market list --mine
```

**Expected output:** offer table (possibly empty), exit 0.

Both output renderers work (`--output` and `--format` are aliases):

```bash
aitbc market list --output json
aitbc market list --format json
```

**Expected output:** a JSON array of offer rows, exit 0.

```bash
aitbc market match --output json
aitbc market match --format json
```

**Expected output:** `{"chain_id": "bc-2", "matches": [...]}` — the
chain-side match listing, exit 0.

```bash
aitbc market providers --output json
aitbc market providers --format json
```

**Expected output:** JSON array of per-provider rows (`Services`,
`Offers`, `Active`, `Rating`), exit 0.

### Step 2: Provider-side listings (expected-refusal / drift)

`offer-list` reads the provider's own offers; on this node the hub's
`/v1/market/offers` answers with a bare JSON array the CLI does not
accept — a drift recorded for registration, the flags are still
exercised:

```bash
aitbc market offer-list --service-type ipfs --status active --output json
```

**Expected output:** `Error listing offers: …/v1/market/offers returned
a JSON array, not an object…` (exit 1 — drift, same `get_json()` shape
class as the trade-family arrays).

```bash
aitbc market offer-list --format json
```

**Expected output:** same refusal.

### Step 3: Payment ledger lookups (expected-refusal)

`payment` reads the coordinator's `job_payments` ledger scoped to the
caller's credential:

```bash
aitbc market payment --job-id nosuch-mo1
```

**Expected output:** `HTTP 403: the stored credential does not own this
job's payment (Not authorized for this payment).` (exit 1).

```bash
aitbc market payment --payment-id nosuch-mo1
```

**Expected output:** `No payment found (404).` (exit 1).

### Step 4: Exchange read + money-path flags (ok / expected-refusal)

`exchange list-deposits` is a free read of the local exchange ledger:

```bash
aitbc market exchange list-deposits --status pending --limit 5
```

**Expected output:** `No deposits found with status 'pending'` (exit 0).

`withdraw-eth` is admin-only and would send real ETH — it asks for
confirmation first, and `n` at the prompt cancels before web3 is even
imported. `<<< n` feeds the refusal; `--address` is exercised for free:

```bash
aitbc market exchange withdraw-eth --amount 0.001 --address 0x0000000000000000000000000000000000000001 <<< n
```

**Expected output:** `Withdrawing 0.001 ETH to 0x0000…0001`,
`Confirm withdrawal? [y/N]: Cancelled` (exit 0 — nothing sent).

`deposit-eth` would sign a real Sepolia transaction, but the
`--bridge-address` value is validated before any signing, so a bogus
address is a free refusal that carries `--ait-address` and `--gas`
along:

```bash
aitbc market exchange deposit-eth --amount 0.001 --ait-address 0x0000000000000000000000000000000000000001 --bridge-address notanaddress --gas 25000
```

**Expected output:** `Using wallet file: …`,
`Invalid bridge deposit address: notanaddress` (exit 1 — refused before
signing; nothing sent).

### Step 5: Ratings (expected-refusal)

`rate` on an unknown service id is refused by the market with a 404 —
`--rating`, `--comment`, `--reviewer-id` and `--market-url` ride along:

```bash
aitbc market rate --service-id nosuch-mo1 --rating 3 --comment 'mo1 probe' --reviewer-id mo1 --market-url https://hub.aitbc.bubuit.net
```

**Expected output:** `No such service: nosuch-mo1` (exit 1).

```bash
aitbc market ratings --service-id nosuch-mo1 --limit 5 --offset 0 --market-url https://hub.aitbc.bubuit.net
```

**Expected output:** `No such service: nosuch-mo1` (exit 1).

`sync-ratings` reads the local market service's unsynced list first —
on a node with no local market service it refuses on connect, and
`--limit` is exercised:

```bash
aitbc market sync-ratings --remote-url http://localhost:1 --limit 5
```

**Expected output:** `Network error during sync: GET request failed …
localhost:8102 … Connection refused` (exit 1).

### Step 6: IPFS download and job cancel (expected-refusal)

`download` accepts `--access-key`, `--cid`, `--output-path` and `--wait`;
a CID that does not exist is refused by the local Kubo daemon:

```bash
aitbc market download --access-key k-mo1 --cid QmNOSUCHmo1 --output-path /tmp/mo1-dl.bin --wait --output json
```

**Expected output:** `Could not retrieve CID QmNOSUCHmo1` (exit 1 —
`--wait` blocks on the daemon's cat until it fails; nothing written).

```bash
aitbc market download --format json
```

**Expected output:** `Provide a CID, --rental-id, or
--access-key/--access-secret` (exit 1 — CLI-side refusal).

`cancel` POSTs to the market service; an unknown job id is a 404:

```bash
aitbc market cancel --job-id nosuch-mo1 --reason mo1_probe --output json
aitbc market cancel --job-id nosuch-mo1 --format json
```

**Expected output:** `Market cancel request failed: POST request
failed: 404 Client Error: Not Found for url:
…/v1/market/jobs/nosuch-mo1/cancel` (exit 1).

`escrow refund` tries the coordinator first, then falls back to the
chain rpc — for an unknown job both refuse:

```bash
aitbc market escrow refund --job-id nosuch-mo1 --reason mo1_probe
```

**Expected output:** `Coordinator refund unavailable for job nosuch-mo1
(no coordinator payment) — falling back to the chain rpc` then
`Failed to refund escrow for job nosuch-mo1: …` (exit 1 — local rpc 503
settlement-key refusal, hub 403 API-key refusal; nothing refunded).

### Step 7: Provider-signed offer paths (expected-refusal, wallet)

`offer` and `offer-disable` sign with the provider wallet. Pointing
`SHOP_WALLET_ADDRESS` at an address no wallet file controls is a free
abort before any signing — every offer flag rides along:

```bash
SHOP_WALLET_ADDRESS=0x0000000000000000000000000000000000000001 aitbc market offer --service-type hermes --model-or-variant mo1 --price 1 --description 'mo1 probe' --context-window 8192 --gpu-name 'NOSUCH GPU' --gpu-offer-id gpu-mo1 --disk-quota-mb 50
```

**Expected output:** `SHOP_WALLET_ADDRESS 0x0000…0001 matches no wallet
file (searched AITBC_WALLET_DIR, ~/.aitbc/wallets,
/var/lib/aitbc/wallets); pass --wallet or --wallet-path` followed by
`Error creating software offer: …` (exit 1 — nothing registered).

```bash
SHOP_WALLET_ADDRESS=0x0000000000000000000000000000000000000001 aitbc market offer-disable --plugin-id nosuch-mo1 --output json
SHOP_WALLET_ADDRESS=0x0000000000000000000000000000000000000001 aitbc market offer-disable --plugin-id nosuch-mo1 --format json
```

**Expected output:** same wallet refusal, `Error disabling offer: …`
(exit 1 — nothing removed).

The group-level `--wallet` form refuses identically:
`aitbc market --wallet nosuch-mo1 offer …` ends at
`Wallet 'nosuch-mo1' not found as a file wallet.` (exit 4).

### Step 8: Software-offer job commands (expected-refusal)

`hermes`, `run`, `process`, `transcribe` and `host` all resolve the
offer first; an unknown offer id aborts before the wallet is even
loaded, so every job flag is exercised for free:

```bash
aitbc market hermes --offer-id-or-plugin-id nosuch-mo1 --prompt 'mo1 probe' --max-time 5 --track --proposer 0x0000000000000000000000000000000000000001 --output json
aitbc market hermes --offer-id-or-plugin-id nosuch-mo1 --prompt 'mo1 probe' --format json
```

**Expected output:** `Offer 'nosuch-mo1' not found on hub` then
`Error running Hermes job:` (exit 1).

```bash
aitbc market run --offer-id-or-plugin-id nosuch-mo1 --prompt 'mo1 probe' --max-tokens 8 --stream --language en --task transcribe --transcript-format text --media-format webm --codec vp9 --resolution 720p --bitrate 1M --max-time 5 --days 1 --no-pin --track --proposer 0x0000000000000000000000000000000000000001 --output json
aitbc market run --offer-id-or-plugin-id nosuch-mo1 --prompt 'mo1 probe' --format json
```

**Expected output:** `Offer 'nosuch-mo1' not found on hub` then
`Error running job:` (exit 1).

```bash
aitbc market process --offer-id-or-plugin-id nosuch-mo1 --input-file /tmp/mo1.mp4 --bitrate 1M --output json
aitbc market process --offer-id-or-plugin-id nosuch-mo1 --input-file /tmp/mo1.mp4 --format json
aitbc market process --offer-id-or-plugin-id nosuch-mo1 --input-file /tmp/mo1.mp4 --output-container webm --codec vp9 --resolution 720p
```

**Expected output:** `Offer 'nosuch-mo1' not found on hub` then
`Error processing video:` (exit 1 — `--input-file` must exist, hence the
fixture file).

```bash
aitbc market transcribe --offer-id-or-plugin-id nosuch-mo1 --audio-file /tmp/mo1.mp3 --language en --task translate --output-format srt --output json
aitbc market transcribe --offer-id-or-plugin-id nosuch-mo1 --audio-file /tmp/mo1.mp3 --format json
```

**Expected output:** `Offer 'nosuch-mo1' not found on hub` then
`Error transcribing audio:` (exit 1 — `--audio-file` must exist).

```bash
aitbc market host --offer-id-or-plugin-id nosuch-mo1 --cid-or-file QmNOSUCHmo1 --no-pin --proposer-id 0x0000000000000000000000000000000000000001 --output json
aitbc market host --offer-id-or-plugin-id nosuch-mo1 --cid-or-file QmNOSUCHmo1 --pin --format json
```

**Expected output:** `Offer 'nosuch-mo1' not found on hub` (exit 1).

### Step 9: Protected GPU rental rail (expected-refusal)

`gpu quote` POSTs to the coordinator; an unknown GPU id is refused:

```bash
aitbc market gpu quote --gpu-id gpu-mo1 --buyer-id 0x0000000000000000000000000000000000000001 --duration-hours 1 --gpu-count 1 --max-ait 1 --settlement native --json-output
```

**Expected output:** `Failed to get quote: POST request failed: 404
Client Error: Not Found for url: …/c/v1/market/gpu/quote` (exit 1 —
`--buyer-id` must be a wallet address on the native rail; a non-address
is refused even earlier, at parse time).

`gpu buy` verifies the operator-signed quote before any funding, so the
fixture quote without a signature is a free refusal that carries every
flag including the required `--buyer-id`/`--job-id`/`--duration-hours`:

```bash
aitbc market gpu buy --gpu-id gpu-mo1 --buyer-id 0x0000000000000000000000000000000000000001 --job-id job-mo1 --duration-hours 1 --settlement native --wallet nosuch-mo1 --energy-quote /tmp/mo1-quote.json --max-ait 1 --yes --json-output
```

**Expected output:** `Quote verification failed: Quote has no operator
signature and no operator address was configured (invalid_signature;
expected id from resolved --chain-id/CHAIN_ID/RPC probe)` (exit 1 —
nothing funded).

`--wallet-path` on `buy` rides on the same refusal:

```bash
aitbc market gpu buy --gpu-id gpu-mo1 --buyer-id 0x0000000000000000000000000000000000000001 --job-id job-mo1 --duration-hours 1 --wallet-path /tmp/nosuch-mo1.json --energy-quote /tmp/mo1-quote.json --yes
```

**Expected output:** same `Quote verification failed` line (exit 1).

`gpu refund` loads the wallet first:

```bash
aitbc market gpu refund --job-id job-mo1 --wallet nosuch-mo1 --reason mo1_probe --yes --json-output
```

**Expected output:** `Wallet 'nosuch-mo1' not found as a file wallet.`
(exit 4 — wallet refusal before signing).

```bash
aitbc market gpu refund --job-id job-mo1 --wallet-path /tmp/nosuch-mo1.json --yes
```

**Expected output:** `No wallet password available and no TTY for a
prompt…` (exit 1 — the password check precedes the file-exists check;
noted as noise).

`gpu release` and `gpu status` hit the coordinator with an unknown job:

```bash
aitbc market gpu release --job-id job-mo1 --yes --json-output
```

**Expected output:** `Release failed: POST request failed: 404 Client
Error: Not Found for url: …/c/v1/jobs/job-mo1/accept` (exit 1).

```bash
aitbc market gpu status --job-id job-mo1 --json-output
```

**Expected output:** `Failed to get status: GET request failed: 401
Client Error: Unauthorized for url: …/c/v1/market/gpu/status/job-mo1`
(exit 1 — the hub coordinator wants a client credential for the read).

---

## Exit-class summary

| exit class | options |
|---|---|
| ok (exit 0) | `list` `--provider`/`--status`/`--sort`/`--mine`/`--output`/`--format`, `match`/`providers` `--output`/`--format`, `exchange list-deposits` `--status`/`--limit`, `exchange withdraw-eth` `--address` (cancelled at prompt) |
| expected-refusal exit 1 | `payment` `--job-id`/`--payment-id` (403/404), `rate`/`ratings` `--market-url` + `--comment`/`--reviewer-id`/`--rating`/`--limit`/`--offset` (404), `sync-ratings` `--limit` (conn refused), `download` `--access-key`/`--cid`/`--output-path`/`--wait`/`--output`/`--format`, `cancel` `--reason`/`--output`/`--format` (404), `exchange deposit-eth` `--ait-address`/`--bridge-address`/`--gas` (invalid address), `offer`/`offer-disable` flags (SHOP_WALLET_ADDRESS abort), `hermes`/`run`/`process`/`transcribe`/`host` flag families (offer not found), `escrow refund` `--reason` (coordinator miss + rpc 503/403), `gpu quote`/`buy`/`release`/`status`/`refund --wallet-path` |
| expected-refusal exit 4 (wallet not found) | `gpu refund` `--wallet`/`--reason`/`--yes`/`--json-output`, group `--wallet` on `offer`/`offer-disable`/`deposit-eth` |
| drift exit 1 | `offer-list` `--service-type`/`--status`/`--output`/`--format` — hub `/v1/market/offers` returns a bare JSON array (`get_json()` shape drift, same class as the trade arrays; registered separately) |
| 🔒 by design | `market`/`gpu buy`/`gpu refund` `--password`, `--password-file`, `--password-stdin`, exchange `--password-*` — never placed in docs |

**Noise noted (not drift):** `market list --provider/--status/--sort`
warns `Market service not available at http://127.0.0.1:8102` on a node
without a local market service before falling back to the chain listing;
`gpu refund --wallet-path` demands a password before checking that the
path exists; `gpu status` needs a coordinator client credential even for
a read.

**Drift found (flagged for registration, not fixed here):** hub
`/v1/market/offers` returns a bare JSON array —
`aitbc market offer-list` aborts `returned a JSON array, not an
object. Use get_json()…` on every invocation, same shape class as the
`market jobs`/`trade` array drift.

---

## See Also

- **Scenario 07**: [AI Job Submission](./07_ai_job_submission.md)
- **Scenario 75**: [Market Escrow & Jobs Options](./75_market_escrow_jobs_options.md)
- **Scenario 76**: [Bridge CLI Options](./76_bridge_options.md)

---

*Last updated: 2026-10-26 (MARKET-OPTS-1 option coverage)*
*Version: 1.0*
