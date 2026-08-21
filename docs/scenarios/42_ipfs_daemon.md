# Scenario 42: Real IPFS daemon behind `aitbc ipfs`

## Goal

Run a real Kubo IPFS daemon behind the canonical `aitbc ipfs` commands so
content is added and retrieved using real CIDs, and two AITBC nodes can fetch
content from each other.

## Preconditions

- `aitbc-ipfs.service` is installed, enabled, and running.
- The Kubo binary is in `/usr/local/bin/ipfs`.
- `IPFS_PATH=/var/lib/aitbc/ipfs-daemon` and `HOME=/var/lib/aitbc/ipfs-daemon`
  are set in the service.

## Steps

1. Start the daemon (if not already):
   ```bash
   sudo systemctl start aitbc-ipfs
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
