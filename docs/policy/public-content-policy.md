# Public content policy — forum messages

Status: **published** (16 Oct 2026). The moderation notice on the messages
page carries this wording; the report sentence renders the `CONTACT_EMAIL`
value from `/etc/aitbc/website.env` on the hub.

## What the chain stores

Forum posts, replies and moderation actions are `MESSAGE` transactions.
Once a transaction is sealed into a block it is replicated to every node
and **cannot be edited or removed** — not by the poster, not by a
moderator, not by the operator. Message bodies are public; anyone running
a node or reading the RPC can see the full sealed history, including rows
that were later hidden.

## What the website shows — and what it does not

The public messages page renders the chain's default read view:

- Rows a topic moderator has **hidden** are excluded from the default
  view, as are rows posted **after a lock** within the locked scope.
  Hidden means hidden from the page, not deleted — the sealed row still
  exists on every node and remains visible through RPC reads that ask
  for it (e.g. `include_hidden`).
- Before display, message text passes through `sanitizeChainText`
  (`website/messages.js`, mirrored by `aitbc/textsafety.py`): bidi
  override/isolate controls, zero-width characters, and hidden-text-
  capable codepoints are shown as visible `[U+XXXX]` placeholders. The
  sanitiser changes rendering only; it does not change what was sealed.

## What topic moderators can and cannot do

Each topic's founding poster is its first moderator, and moderators can
grant or revoke the role within their own topic. A moderator's actions
are **topic-local view actions only**:

- `hide` / `unhide` a message — remove it from, or restore it to, the
  default view.
- `pin` / `unpin` — change ordering within the topic.
- `lock` / `unlock` — mark a topic or reply subtree; posts made during a
  lock carry a permanent `after_lock` flag.
- `mod_grant` / `mod_revoke` — manage the topic's moderator set.

Moderators **cannot** edit bodies, delete sealed rows, moderate other
people's topics, or act globally — there is deliberately no global
moderation role. Votes and reputation are separate signals; reputation
is display-only and grants no authority.

## Reporting content

To report a post — for example content you believe is illegal — contact
the operator:

> **[OPERATOR CONTACT — TO BE FILLED]**

Include the topic name and the transaction hash of the message (shown on
the message page and in the explorer), plus a line on why it is being
reported.

## What the operator can do

The only removal-from-view mechanism is the **on-chain `hide` action**,
and it works for the operator only where the operator's wallet is the
topic's founder or has been granted that topic's moderator role. Even
then it changes only the default view — the sealed row remains on the
chain and remains readable via `include_hidden`.

**No site-side denylist or page-level hide exists, and none is planned**
(operator decision, 16 Oct 2026). The website stays read-only.

## Reporter-facing block (for the page footer or about text)

Exact wording, ready to paste once the operator fills the contact:

> **User content, moderated only by topic moderators.** Posts are
> replicated to every node and cannot be edited or deleted. To report
> illegal or abusive content, contact [OPERATOR CONTACT — TO BE FILLED]
> with the topic name and the message's transaction hash.

## What is out of reach

- Sealed rows are permanent. There is no delete, on-chain or off.
- The operator cannot alter another node's view of the chain.

## Operator-confirmed positions (16 Oct 2026)

- **Retention** — sealed rows are retained permanently.
- **Response time** — no response time is promised.
- **Anonymous reports** — reports are accepted without identifying the
  reporter.
- **Jurisdiction** — no jurisdiction wording; none has been chosen.

## Contact

The contact is `CONTACT_EMAIL` in `/etc/aitbc/website.env` on the hub
(currently `andreas.fleckl@bubuit.net`); `render-website.sh` writes it
between the `aitbc-contact` markers on the messages page. Filled 16 Oct
2026 — no open items remain.
