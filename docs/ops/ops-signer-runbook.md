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
cd /opt/aitbc && venv/bin/python -m aitbc_cli wallet create --wallet-name ops
# copy the address it prints — verify with:
venv/bin/python -m aitbc_cli wallet address --wallet-name ops
```

The wallet lands at `/root/.aitbc/wallets/ops.json` for root (or
`/var/lib/aitbc/wallets/ops.json` for the aitbc user — see step 4's
`OPS_WALLET_PATH`). Record the printed `0x…` address; it is needed in
step 2's sender/recipient check and the post-canary balance check.

## Step 2 — fund it with 50 AIT

Send from whichever funded wallet the operator chooses (e.g. treasury).
**Check the sender address the CLI prints before confirming** — the
S-10 run taught us `--wallet-name` resolves different directories for
root vs the aitbc user:

```bash
cd /opt/aitbc && venv/bin/python -m aitbc_cli wallet address --wallet-name treasury
# must print the intended sender (e.g. 0x4059cf2e…). If it differs, pass
# --wallet-path explicitly.

venv/bin/python -m aitbc_cli wallet send \
  --wallet-name treasury \
  --to-address <ops-address-from-step-1> \
  --amount 50 --fee 0.0001
```

Verify the funding leg sealed:

```bash
sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
  "SELECT balance, nonce FROM account WHERE address='<ops-address>'"
# expect 1,800,000,000 units (50 AIT)
```

## Step 3 — write the credential and the allow-list

```bash
install -d -m 700 -o root -g root /etc/aitbc/credentials
# encrypt the wallet password as a systemd credential (interactive):
systemd-creds encrypt --name=ops-wallet-pass - /etc/aitbc/credentials/ops-wallet-pass
# type the ops-wallet password when prompted, chmod:
chmod 600 /etc/aitbc/credentials/ops-wallet-pass

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
OPS_WALLET_PATH=/root/.aitbc/wallets/ops.json
OPS_SIGNER_RPC_URL=http://127.0.0.1:8202
EOF
# set OPS_WALLET_PATH to wherever step 1 actually put the wallet.

groupadd --system aitbc-ops   # the agent/operator client accounts join this group
install -m 644 -o root -g root \
  /opt/aitbc/apps/ops-signer/aitbc-ops-signer.service \
  /etc/systemd/system/aitbc-ops-signer.service
systemctl daemon-reload
systemctl enable --now aitbc-ops-signer
systemctl status aitbc-ops-signer --no-pager
journalctl -u aitbc-ops-signer -n 20 --no-pager
# expect: "ops signer starting: sock=/run/aitbc-ops-signer.sock group=aitbc-ops caps=36000000/180000000"
ls -l /run/aitbc-ops-signer.sock   # srw-rw---- root aitbc-ops
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

## Refusal checks (optional pre-flight)

```bash
# not allow-listed -> {"ok":false,"reason":"not_allowlisted"}
# missing memo      -> {"ok":false,"reason":"bad_memo"}
# amount > cap      -> {"ok":false,"reason":"over_tx_cap"}
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
