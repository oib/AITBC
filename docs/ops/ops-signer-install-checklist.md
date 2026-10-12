# Ops signer install checklist (SEC-3)

One page. Run every step on **hub** as root, in order. Each step has the
command, the expected output, and a **stop condition** — on a stop
condition, stop and resolve before continuing. Full context and rollback
detail: [ops-signer-runbook.md](ops-signer-runbook.md).

Legend: `expect` = what success looks like; `STOP` = do not continue.

1. **Create the ops wallet** (operator types the password at the prompt —
   it appears in no file or argument):

   ```bash
   cd /opt/aitbc && AITBC_WALLET_DIR=/var/lib/aitbc/wallets \
     venv/bin/python -m aitbc_cli wallet create --name ops
   ```

   - expect: prompts for + confirms a new password, prints a `0x…` address
   - verify: `venv/bin/python -m aitbc_cli wallet --wallet-name ops address` prints the same `0x…`
   - STOP if the file did not land at `/var/lib/aitbc/wallets/ops.json` (`ls -l /var/lib/aitbc/wallets/ops.json`) — the unit's `ProtectHome=yes` makes `/root/.aitbc` invisible

2. **Fund the wallet with 50 AIT** (operator runs the transfer from their
   own wallet; sender address checked first — the S-10 lesson):

   ```bash
   venv/bin/python -m aitbc_cli wallet --wallet-name treasury address   # expect your intended sender
   venv/bin/python -m aitbc_cli wallet --wallet-name treasury send \
     --to-address <ops-address> --amount 50 --fee 0.0001
   sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
     "SELECT balance FROM account WHERE address='<ops-address>'"
   ```

   - expect: send prints a sealed tx hash; balance query returns `1800000000`
   - STOP if the sender address shown is not the intended funding wallet, or the balance does not reach 1,800,000,000 units within a few blocks

3. **Encrypt the wallet password as a systemd credential** (operator types
   the ops password at the prompt):

   ```bash
   install -d -m 700 -o root -g root /etc/aitbc/credentials
   systemd-creds encrypt --name=ops-wallet-pass - /etc/aitbc/credentials/ops-wallet-pass
   chmod 600 /etc/aitbc/credentials/ops-wallet-pass && ls -l /etc/aitbc/credentials/ops-wallet-pass
   ```

   - expect: prompts once, writes the credential file mode 600 root:root (hub seals against the host key — `systemd-analyze has-tpm2` is `partial`)
   - STOP on any encrypt error or a file that is not `-rw------- root root`

4. **Write the env file** (policy values; not secret):

   ```bash
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
   ```

   - expect: `cat /etc/aitbc/ops-signer.env` shows exactly those 10 lines, `OPS_WALLET_PATH` matching step 1's actual location
   - STOP if `OPS_WALLET_PATH` points under `/root` or `/home`

5. **Install the allow-list** (shop wallet + S-10 payee only):

   ```bash
   install -m 600 -o root -g root \
     /opt/aitbc/apps/ops-signer/ops-signer.allow.example /etc/aitbc/ops-signer.allow
   cat /etc/aitbc/ops-signer.allow
   ```

   - expect: two uncommented addresses — `0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2` and `0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4`
   - STOP if any other uncommented line appears (a malformed line refuses the whole file)

6. **Create the group, install and start the unit:**

   ```bash
   groupadd --system aitbc-ops
   install -m 644 -o root -g root \
     /opt/aitbc/apps/ops-signer/aitbc-ops-signer.service \
     /etc/systemd/system/aitbc-ops-signer.service
   systemctl daemon-reload && systemctl enable --now aitbc-ops-signer
   journalctl -u aitbc-ops-signer -n 20 --no-pager
   ls -l /run/aitbc-ops-signer.sock
   ```

   - expect: journal line starting `ops signer starting: sock=/run/aitbc-ops-signer.sock group=aitbc-ops caps=36000000/180000000` (ends with ` allow_file=/etc/aitbc/ops-signer.allow`); socket `srw-rw---- root aitbc-ops`
   - STOP if the unit fails, restarts in a loop, or the socket is missing/wrong mode — read the journal first

7. **Dry-run request** (all checks, signs nothing):

   ```bash
   python3 - <<'EOF'
   import json, socket
   s = socket.socket(socket.AF_UNIX); s.connect("/run/aitbc-ops-signer.sock")
   s.sendall(json.dumps({"op":"sign_payment","to":"0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                         "amount_units":1,"memo":"SEC-3","dry_run":True}).encode()+b"\n")
   print(s.recv(4096).decode()); s.close()
   EOF
   ```

   - expect: `{"ok": true, "result": "dry_run_pass"}`
   - STOP on `peer_not_in_group` (running shell is not root), `refused`, or `error/internal` — do not canary until dry-run passes

8. **One-unit canary** to an allow-listed address:

   ```bash
   python3 - <<'EOF'
   import json, socket
   s = socket.socket(socket.AF_UNIX); s.connect("/run/aitbc-ops-signer.sock")
   s.sendall(json.dumps({"op":"sign_payment","to":"0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                         "amount_units":1,"memo":"SEC-3"}).encode()+b"\n")
   print(s.recv(4096).decode()); s.close()
   EOF
   ```

   - expect: `{"ok": true, "result": "signed", "tx_hash": "0x…"}`
   - STOP on any refusal — check `journalctl -u aitbc-ops-signer` and `/var/lib/aitbc/ops-signer-audit.log`

9. **Audit + on-chain verification:**

   ```bash
   tail -3 /var/lib/aitbc/ops-signer-audit.log
   sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
     "SELECT sender,recipient,value,fee FROM \"transaction\" WHERE tx_hash='<pasted hash>'"
   ```

   - expect: audit line carries the tx hash + memo + amount only (no key, no password); the sealed row shows sender = ops address, value = 1, fee = 3600
   - STOP if the audit line contains anything besides time/memo/to/amount/result/tx-hash, or the tx does not seal

10. **Rollback** (when needed — full reversal):

    ```bash
    systemctl disable --now aitbc-ops-signer
    rm /etc/systemd/system/aitbc-ops-signer.service && systemctl daemon-reload
    rm /etc/aitbc/credentials/ops-wallet-pass
    sqlite3 "file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro" \
      "SELECT balance FROM account WHERE address='<ops-address>'"   # remaining float
    venv/bin/python -m aitbc_cli wallet --wallet-path /var/lib/aitbc/wallets/ops.json send \
      --to-address <funding-wallet> --amount <balance minus ~0.001 fee> --fee 0.0001
    ```

    - expect: unit gone, credential gone, the remaining float (50 AIT less the canary and fees) back at the funding wallet
    - the wallet file, env file, allow-list, ledger and audit log may stay for forensics; delete `/var/lib/aitbc/wallets/ops.json` last if retiring the wallet
