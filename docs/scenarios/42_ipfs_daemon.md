# Scenario 42: Real IPFS daemon behind `aitbc ipfs`

## Goal

> **Live vs. simulated:** `aitbc ipfs` commands are **live** once the `aitbc-ipfs` Kubo daemon is running. If the daemon is not running, the CLI falls back to a local filesystem CID shim.


Run a real Kubo IPFS daemon behind the canonical `aitbc ipfs` commands so
content is added and retrieved using real CIDs, and two AITBC nodes can fetch
content from each other.

## Preconditions

> **Production note (2026-09):** the fleet runs `aitbc-island-ipfs` — a Kubo
> daemon on a private pnet swarm (swarm :4002, API `127.0.0.1:5002`, gateway
> `127.0.0.1:8081`) gated by a shared `swarm.key`. The public `aitbc-ipfs`
> daemon (:4001/:5001) this scenario originally targeted is retired; the steps
> below still apply to any Kubo daemon — substitute the island API port where
> needed. Paid hosting between nodes uses `aitbc market host` /
> `aitbc market download` against an `ipfs`-service-type offer (see
> `docs/DESIGN_CYCLE.md` P2.9).

- `aitbc-island-ipfs.service` (or the legacy `aitbc-ipfs.service` on a dev node)
  is installed, enabled, and running.
- The Kubo binary is in `/usr/local/bin/ipfs`.
- The island repo lives under `/var/lib/aitbc/data/ipfs-island/<island-id>`
  with a `swarm.key` provisioned by the hub.

## Steps

1. Start the daemon (if not already):
   ```bash
   sudo systemctl start aitbc-island-ipfs   # legacy dev nodes: aitbc-ipfs
   ```

2. Upload a file:
   ```bash
   echo "AITBC IPFS cross-node test" > /tmp/ipfs_test.txt
   aitbc ipfs upload --file /tmp/ipfs_test.txt
   ```

3. Expected output:
   ```json
   {"success": true, "data": {"cid": "Qm...", "size": 26, "name": "ipfs_test.txt"}}
   ```

4. Download by CID:
   ```bash
   aitbc ipfs download <CID> --output /tmp/ipfs_out.txt
   cat /tmp/ipfs_out.txt
   ```

5. Cross-node retrieval:
   - On the second node, run:
     ```bash
     aitbc ipfs download <CID> --output /tmp/ipfs_out_remote.txt
     cat /tmp/ipfs_out_remote.txt
     ```
   - The content should be retrieved over the IPFS swarm/DHT.
   - Both nodes can be left unpeered; the public DHT resolves the CID as long
     as the originating daemon is online.

6. List pinned content:
   ```bash
   aitbc ipfs list
   ```

## Notes

- `aitbc ipfs` probes `http://127.0.0.1:5001` by default; set `IPFS_API_URL` to
  override.
- If the daemon is not reachable, the command falls back to the filesystem stub
  and prints a warning.
- The old filesystem stub stored content under `/var/lib/aitbc/ipfs` with
  synthetic `Qm...` CIDs; the daemon now returns real IPFS CIDs.


## Validation

- `aitbc ipfs upload` returns a real CID (e.g. `QmSoASxb8aNVGk3pNWpZvXEZTQKxjGeu9bvpYHuo5bP1VJ`).
- `aitbc ipfs download <CID>` writes the original bytes back.
- `aitbc ipfs list` shows the pinned CID as `recursive`.
- Cross-node `aitbc ipfs download <CID>` on the other node succeeds and the
  content matches.

## Files

- `cli/aitbc_cli/commands/ipfs.py` — uses the Kubo HTTP API with filesystem fallback.
- `apps/ipfs/aitbc-ipfs.service` — systemd unit for the Kubo daemon.
