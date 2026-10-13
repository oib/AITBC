# Ops signer rollout runbook (SEC-2)

Operator-only steps for `aitbc-ops-signer` — wallet creation, funding,
credential, allow-list, unit install, canary, rollback. All steps run on
**hub** as root. The agent wrote the code; the operator performs every
step that touches a wallet, a passphrase, or a host file.

Design: [../design/node-held-wallet-access.md](../design/node-held-wallet-access.md)
Operator decisions (12 Oct): 50 AIT float, caps 1 AIT/tx and 5 AIT/day
(`OPS_MAX_PER_TX=36000000`, `OPS_MAX_PER_DAY=180000000`), hub only,
minimal allow-list.

## Step 1 — create the ops wallet

```bash
cd /opt/aitbc && AITBC_WALLET_DIR=/var/lib/aitbc/wallets \
  venv/bin/python -m aitbc_cli wallet create --name ops
# copy the address it prints — verify with:
venv/bin/python -m aitbc_cli wallet --wallet-name ops address
```

The wallet lands at `/var/lib/aitbc/wallets/ops.json`. It **must** live
under `/var/lib/aitbc` — the unit runs with `ProtectHome=yes`, so a
wallet in `/root/.aitbc/wallets` (root's default `AITBC_WALLET_DIR`)
would be invisible to the service. `AITBC_WALLET_DIR` on the `create`
line is what places it correctly; `--wallet-name` is a group-level
option that sits before the subcommand. The CLI creates the file `0644` —
tighten it immediately:

```bash
chmod 600 /var/lib/aitbc/wallets/ops.json
```

Record the printed `0x…` address; it is needed in step 2's
sender/recipient check and the post-canary balance check.

## Step 2 — fund it with 50 AIT

The funding leg is signed on the **IDE host** — the live treasury key
exists only there. On hub, `--wallet-name treasury` resolves to the
**retired** `0x716a…` fee-recipient wallet (~99,457 units), not the live
treasury `0x34FFfAd1…`. Before sending, the sender address must match
`keys/treasury_cold.address` **and** carry the real treasury balance
(address match alone is not enough — check both):

```bash
# on the IDE host, /opt/aitbc — NOT on hub:
cd /opt/aitbc && venv/bin/python -m aitbc_cli wallet --wallet-name treasury address
# must print the live treasury 0x34FFfAd1… — compare with
# keys/treasury_cold.address, then check the on-chain balance is the
# treasury float, not the retired 0x716a… wallet's ~99,457 units.

venv/bin/python -m aitbc_cli wallet --wallet-name treasury send \
  --to-address <ops-address-from-step-1> \
  --amount 50 --fee 0.0001
# (the helper scratch/sec3/fund_ops_wallet.py is staging-only on the IDE
# host and not in the repo — the plain CLI send above is the path)
```

Verify the funding leg sealed:

```bash
sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
  "SELECT balance, nonce FROM account WHERE address='<ops-address>'"
# expect 1,800,000,000 units (50 AIT)
```

## Step 3 — write the credential and the allow-list

```bash
# /etc/aitbc/credentials already exists on hub (root:aitbc 0750) holding
# other credentials — do NOT install -d it. Encrypt via a non-hanging
# recipe — 'systemd-creds encrypt - file' reads stdin SILENTLY until EOF
# (no prompt), so pipe it instead of typing at it:

# bash (hub's root shell):
read -rs OPSPASS && printf %s "$OPSPASS" | \
  systemd-creds encrypt --name=ops-wallet-pass - /etc/aitbc/credentials/ops-wallet-pass
unset OPSPASS
# zsh equivalent: read -rs "OPSPASS?"  — same printf pipeline.
chmod 600 /etc/aitbc/credentials/ops-wallet-pass
# hub's TPM2 reports 'partial' (systemd-analyze has-tpm2): the credential
# is sealed against the host key rather than a TPM — the service's
# systemd-creds decrypt path (or LoadCredentialEncrypted where the mount
# works) handles either.

# allow-list — start from the shipped example, edit to the real list:
install -m 600 -o root -g root \
  /opt/aitbc/apps/ops-signer/ops-signer.allow.example /etc/aitbc/ops-signer.allow
# verify contents (one address per line, comments allowed):
cat /etc/aitbc/ops-signer.allow
```

## Step 4 — install and start the unit

```bash
# ops-signer.env: policy values (root-owned, not a secret file)
install -m 600 -o root -g root /dev/null /etc/aitbc/ops-signer.env
cat >> /etc/aitbc/ops-signer.env <<'EOF'
OPS_SIGNER_SOCK=/run/aitbc-ops-signer.sock
OPS_SIGNER_GROUP=aitbc-ops
OPS_SIGNER_ALLOW_FILE=/etc/aitbc/ops-signer.allow
OPS_MAX_PER_TX=36000000
OPS_MAX_PER_DAY=180000000
OPS_FEE_UNITS=3600
OPS_LEDGER_PATH=/var/lib/aitbc/ops-signer-ledger.db
OPS_AUDIT_LOG=/var/lib/aitbc/ops-signer-audit.log
OPS_WALLET_PATH=/var/lib/aitbc/wallets/ops.json
OPS_SIGNER_RPC_URL=http://127.0.0.1:8202
EOF
# OPS_WALLET_PATH must match where step 1 put the wallet — it must be
# under /var/lib/aitbc (the unit's ProtectHome=yes hides /root).

groupadd --system aitbc-ops   # the agent/operator client accounts join this group
install -m 644 -o root -g root \
  /opt/aitbc/apps/ops-signer/aitbc-ops-signer.service \
  /etc/systemd/system/aitbc-ops-signer.service
systemctl daemon-reload
systemctl enable --now aitbc-ops-signer
systemctl status aitbc-ops-signer --no-pager
journalctl -u aitbc-ops-signer -n 20 --no-pager
# expect a line starting:
#   ops signer starting: sock=/run/aitbc-ops-signer.sock group=aitbc-ops caps=36000000/180000000
#   (the logged line also ends with " allow_file=/etc/aitbc/ops-signer.allow")
ls -l /run/aitbc-ops-signer.sock   # srw-rw---- root aitbc-ops
# the socket can appear a moment after 'systemctl enable --now' returns —
# if ls shows nothing, re-run 'ls -l /run/aitbc-ops-signer.sock' once
# before treating it as a failure.
```

## Step 5 — dry-run, then the 1-unit canary

Dry-run runs every check (peer, allow-list, caps, memo) without signing
or sending — safe pre-flight:

```bash
python3 - <<'EOF'
import json, socket
s = socket.socket(socket.AF_UNIX); s.connect("/run/aitbc-ops-signer.sock")
s.sendall(json.dumps({"op":"sign_payment","to":"<allow-listed addr>",
                      "amount_units":1,"memo":"SEC-2","dry_run":True}).encode()+b"\n")
print(s.recv(4096).decode()); s.close()
EOF
# expect: {"ok": true, "result": "dry_run_pass"}
```

Canary — a 1-unit send to an allow-listed address:

```bash
python3 - <<'EOF'
import json, socket
s = socket.socket(socket.AF_UNIX); s.connect("/run/aitbc-ops-signer.sock")
s.sendall(json.dumps({"op":"sign_payment","to":"<allow-listed addr>",
                      "amount_units":1,"memo":"SEC-2"}).encode()+b"\n")
print(s.recv(4096).decode()); s.close()
EOF
# expect: {"ok": true, "result": "signed", "tx_hash": "0x…"}
```

Verify on-chain (read-only, on hub):

```bash
sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
  "SELECT block_height,type,sender,recipient,value,fee FROM \"transaction\"
    WHERE tx_hash='<pasted hash>'"
# expect TRANSFER, sender = ops address, value = 1, fee = 3600
tail -3 /var/lib/aitbc/ops-signer-audit.log   # one line, tx hash only
```

## Diagnosing `error`/`internal` on the canary

The journal carries a `sign request failed: <ClassName>: <message>`
WARNING per failed request since SEC-3b. To isolate the stage directly,
run this as root on hub — it exercises the same credential path the unit
sees and prints stage names + exception **class names only**:

```bash
set -a; . /etc/aitbc/ops-signer.env; set +a
cd /opt/aitbc && PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/ops-signer/src \
  venv/bin/python - <<'EOF'
import sys
from aitbc_ops_signer.config import Config
from aitbc_ops_signer import signer

cfg = Config.from_env()

def stage(name, fn):
    try:
        out = fn()
    except Exception as e:
        print(f"{name}: FAIL ({type(e).__name__})")
        sys.exit(1)
    print(f"{name}: ok")
    return out

pw = stage("credential", lambda: signer._credential_password(cfg.credential_file))
wallet = stage("wallet decrypt", lambda: signer._load_wallet(cfg.wallet_path, pw))
key = stage("private key", lambda: signer._private_key(wallet))
http = signer.Signer(cfg)._http()
chain_id = stage("chain id", lambda: signer.resolve_chain_id(http))
stage("nonce", lambda: signer.fetch_nonce(http, wallet["address"]))
EOF
```

A plain root shell reproduces the unit's credential view on hub's LXC —
`CREDENTIALS_DIRECTORY` is unset there, so this runs the same
`systemd-creds decrypt` fallback the service uses.

## Refusal checks (optional pre-flight)

```bash
# not allow-listed -> {"ok":false,"result":"refused","reason":"not_allowlisted"}
# missing memo      -> {"ok":false,"result":"refused","reason":"bad_memo"}
# amount > cap      -> {"ok":false,"result":"refused","reason":"over_tx_cap"}
```

## Rollback

```bash
systemctl disable --now aitbc-ops-signer
rm /etc/systemd/system/aitbc-ops-signer.service && systemctl daemon-reload
```

The wallet file, allow-list, credential, ledger and audit log all stay
in place (nothing is deleted). If the wallet itself is ever suspect:
sweep its balance back to the funding wallet (normal operator send),
then re-run steps 1–5 with a fresh `ops-2` wallet and an updated
`OPS_WALLET_PATH`.

## What stays operator-owned

- the passphrase itself (typed once into `systemd-creds encrypt`);
- the float amount and any future changes to the caps;
- adding/removing allow-list entries;
- joining users to the `aitbc-ops` group (`usermod -aG aitbc-ops <user>`).
