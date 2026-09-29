# Escrow routing: send escrow operations to the node that created the escrow

Settlement routes (`POST /escrow/create`, `/{id}/lock`, `/{id}/settle`,
`/{id}/refund`, `/{id}/dispute`, `/{id}/resolve`) serve the `escrow` table,
which is **service-local state**: the row is written by the node that
accepted the create call — normally the customer-facing node the client
talks to — and is not replicated through consensus or aux sync.

Consequences for operators:

- Route escrow create/release/refund to the node where the escrow was
  created (normally the customer node).
- A `404 "Escrow not found"` answer from another node is expected
  submit-time divergence — the row simply does not exist in that node's
  service DB — not corruption, not a sync failure, not a fork.
- The 404 on a missing row is the defined behavior (see
  `rpc/routers/settlement.py`: get at :181, dispute at :280, resolve at
  :317; refund maps service-level "not found" to 404 at :160).

## Design TODO

Aux service tables like `escrow` should be **derivable from sealed
`ESCROW_*` history** rather than submit-time writes: the chain already
records `ESCROW_LOCK` / `ESCROW_RELEASE` / `ESCROW_REFUND` transactions in
every block, so a node could rebuild its escrow view by replaying sealed
history instead of depending on which node fielded the original POST.
Until that derivation exists, the routing rule above stands.
