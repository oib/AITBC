"""Software-service offers and on-chain anchor resolution mixin.

Cluster moved verbatim from ``offers.py`` (issue #1860, phase 6 band split):
the software-service list/get/register/unregister endpoints plus the
GPU_MARKET/GPU_REGISTER anchor machinery that confirms them on-chain.
``_OffersMixin`` inherits this mixin so every ``self.*`` call keeps
resolving and the ``MarketService`` MRO is unchanged.
"""

import time
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market.offer_registration import verify_offer_registration
from aitbc.utils.chain_id import resolve_chain_id

from ...config import settings
from ...domain.market import OfferAnchor, SoftwareService
from .core import _CoreMixin
from .shared import (
    _ANCHOR_NEGATIVES_MAX,
    _ANCHOR_NEGATIVE_TTL_SECONDS,
    _GPU_LISTING_DEFAULT_STATUS,
    _OPS_ERRORS,
    _REGISTRATION_FIELDS,
    _gpu_offer_to_service_dict,
    _local_offer_dict,
    max_page_size,
)


logger = get_logger(__name__)


class _OffersSoftwareMixin(_CoreMixin):
    _anchor_negatives: dict[tuple[str, str], float] = {}

    @classmethod
    def _evict_anchor_negatives(cls, now: float) -> None:
        """Drop every entry whose deadline has passed (#819: they were only
        filtered at read time, so the shared map only ever grew)."""
        for stale in [key for key, deadline in cls._anchor_negatives.items() if deadline <= now]:
            del cls._anchor_negatives[stale]

    @classmethod
    def _remember_anchor_negative(cls, key: tuple[str, str], deadline: float) -> None:
        """Record a negative and hold the map at ``_ANCHOR_NEGATIVES_MAX``,
        dropping the entries closest to expiry first."""
        cls._anchor_negatives[key] = deadline
        excess = len(cls._anchor_negatives) - _ANCHOR_NEGATIVES_MAX
        if excess > 0:
            for oldest in sorted(cls._anchor_negatives, key=cls._anchor_negatives.__getitem__)[:excess]:
                del cls._anchor_negatives[oldest]

    async def list_software_services(
        self, service_type: str | None = None, status: str | None = None, chain_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List software services with optional filters - aggregates from blockchain and local database

        v0.6.6: Uses BlockchainRPCClient for blockchain queries with chain_id filter.
        """
        from sqlalchemy import select

        from ...domain.market import SoftwareService

        try:
            # First, try to get offers from blockchain via RPC (v0.6.6: uses BlockchainRPCClient)
            blockchain_offers = await self._blockchain_gpu_offers(chain_id, status)

            # Second, get offers from local database
            query = select(SoftwareService)
            if service_type:
                query = query.where(SoftwareService.service_type == service_type)  # type: ignore[arg-type]
            if status:
                query = query.where(SoftwareService.status == status)  # type: ignore[arg-type]
            query = query.limit(max_page_size())
            result = await self.session.execute(query)
            local_services = result.scalars().all()

            local_offers = [_local_offer_dict(s) for s in local_services]

            # Merge blockchain and local offers, preferring blockchain
            seen_plugin_ids = set()
            merged_offers = []

            # Add blockchain offers first
            for offer in blockchain_offers:
                plugin_id = offer["plugin_id"]
                if plugin_id not in seen_plugin_ids:
                    merged_offers.append(offer)
                    seen_plugin_ids.add(plugin_id)

            # Add local offers that aren't in blockchain
            for offer in local_offers:
                plugin_id = offer["plugin_id"]
                if plugin_id not in seen_plugin_ids:
                    merged_offers.append(offer)
                    seen_plugin_ids.add(plugin_id)

            local_rows = {s.plugin_id: s for s in local_services}
            await self._resolve_offer_anchors(merged_offers, chain_id, local_rows)

            # The merge can exceed the page ceiling (blockchain page + local
            # page); the public list contract is one bounded page (#1543).
            merged_offers = merged_offers[: max_page_size()]

            logger.info(
                "Returning %s total offers (%s from blockchain, %s from local)",
                len(merged_offers),
                len(blockchain_offers),
                len(local_offers),
            )

            return merged_offers
        except Exception as e:
            logger.error("Error in list_software_services: %s: %s", type(e).__name__, str(e))
            raise

    async def _blockchain_gpu_offers(self, chain_id: str | None, status: str | None) -> list[dict[str, Any]]:
        """GPU offers from the chain RPC, minus allocated/malformed rows.

        Failures degrade to whatever was collected (usually empty) so the
        local database listing still answers.
        """
        blockchain_offers: list[dict[str, Any]] = []
        try:
            # Query GPU offers from blockchain with chain_id filter. A GPU its
            # registrant took out of service (GPU_DEREGISTER) stays on the chain
            # as "deactivated"; the default listing leaves it out, and asking
            # for a status explicitly still shows it.
            offers = await self._rpc_client.query_offers(
                chain_id=chain_id,
                status=status if status else _GPU_LISTING_DEFAULT_STATUS,
            )
            for offer in offers:
                # #1566: a GPU holding open on-chain allocations stays
                # status='active' but is spoken for — an allocation does
                # not touch gpu.status. The chain RPC reports the count;
                # nodes predating the field yield 0 and keep old behavior.
                if int(offer.get("active_allocations") or 0) > 0:
                    logger.info(
                        "Skipping allocated GPU offer %s (active_allocations=%s)",
                        offer.get("gpu_id", offer.get("id", "unknown")),
                        offer.get("active_allocations"),
                    )
                    continue
                price_per_hour = offer.get("price_per_hour")
                if price_per_hour is None:
                    logger.warning(
                        "Skipping blockchain offer %s: missing price_per_hour",
                        offer.get("gpu_id", offer.get("id", "unknown")),
                    )
                    continue
                try:
                    blockchain_offers.append(_gpu_offer_to_service_dict(offer, chain_id, settings.hub_rpc_url))
                except _OPS_ERRORS as e:
                    logger.warning("Failed to parse blockchain offer: %s", e)
                    continue

            logger.info("Retrieved %s offers from blockchain RPC (chain_id=%s)", len(blockchain_offers), chain_id)
            # The RPC page is unbounded — cap it before the merge so a
            # large on-chain offer set cannot be materialised and
            # re-merged in full (#1543 residual).
            return blockchain_offers[: max_page_size()]
        except _OPS_ERRORS as e:
            logger.warning("Failed to get offers from blockchain RPC: %s", e)
            return blockchain_offers

    @staticmethod
    def _anchor_belongs_to_provider(anchor_tx: dict[str, Any], offer: dict[str, Any], is_gpu: bool) -> bool:
        """Bind an anchor tx to the offer's provider.

        GPU offers bind on the registrant wallet when ``registered_by`` is
        available — the register tx's authenticated ``sender`` must be that
        wallet, which node labels (``miner_id``) can't prove. Older rows
        without the field fall back to ``payload.miner_id`` matching the
        offer's provider id. Software offers carry the provider's wallet
        address, matching the anchor tx's authenticated ``sender``. Anything
        that can't be bound to the claimed provider is not this offer's
        anchor — an attacker copying an offer_id can't borrow someone else's
        seal.
        """
        provider = offer.get("provider_address") or ""
        if not provider:
            return False
        payload = anchor_tx.get("payload") or {}
        if is_gpu:
            sender = anchor_tx.get("sender") or ""
            registered_by = offer.get("registered_by") or ""
            if registered_by:
                return bool(sender) and canonical_address(sender) == canonical_address(registered_by)
            return payload.get("miner_id") == provider
        sender = anchor_tx.get("sender") or ""
        return bool(sender) and canonical_address(sender) == canonical_address(provider)

    @staticmethod
    def _anchor_binding_key(offer: dict[str, Any], is_gpu: bool) -> str:
        """The offer-side identity an anchor must bind to — what
        ``_anchor_belongs_to_provider`` requires the tx's authenticated
        sender (or, pre-``registered_by``, the miner label) to equal. Stored
        on ``OfferAnchor`` rows: a changed binding forces live re-resolution
        instead of replaying a stale confirmation."""
        provider = str(offer.get("provider_address") or "")
        if is_gpu:
            registered_by = offer.get("registered_by") or ""
            return canonical_address(registered_by) if registered_by else provider
        return canonical_address(provider)

    @staticmethod
    def _anchor_timestamp(anchor_tx: dict[str, Any]) -> tuple[str | None, datetime | None]:
        """Return (iso string for the offer dict, naive datetime for columns).

        Transaction.timestamp is already a string column; numeric only if a
        serializer emitted epoch seconds."""
        ts = anchor_tx.get("timestamp")
        if ts is None:
            return None, None
        if isinstance(ts, str):
            try:
                return ts, datetime.fromisoformat(ts).replace(tzinfo=None)
            except ValueError:
                return ts, None
        dt = datetime.fromtimestamp(ts, UTC)
        return dt.isoformat(), dt.replace(tzinfo=None)

    def _persist_anchor(
        self,
        dbkey: str,
        offer: dict[str, Any],
        is_gpu: bool,
        anchor_tx: dict[str, Any],
        block_ts: datetime | None,
        existing_row: OfferAnchor | None,
        local_rows: dict[str, SoftwareService] | None,
    ) -> bool:
        """Store a verified anchor so later listings skip chain probes.

        Offers backed by a local ``SoftwareService`` take confirmation on the
        row's ``block_*`` columns — which is what ``_local_offer_dict`` reads
        and what the registration allow-list keeps providers from forging.
        On-chain-only offers (GPU bundles) get an ``OfferAnchor`` row keyed
        under the same namespace, bound to the provider identity verified
        now. Returns True when something was written.
        """
        row = local_rows.get(str(offer.get("plugin_id") or "")) if local_rows else None
        if row is not None:
            changed = False
            for attr, value in (
                ("tx_hash", anchor_tx.get("tx_hash")),
                ("block_height", anchor_tx.get("block_height")),
                ("block_hash", anchor_tx.get("block_hash")),
                ("block_proposer", anchor_tx.get("block_proposer")),
                ("block_timestamp", block_ts),
            ):
                if value is not None and getattr(row, attr) != value:
                    setattr(row, attr, value)
                    changed = True
            return changed
        anchor = existing_row if existing_row is not None else OfferAnchor(key=dbkey)
        if existing_row is None:
            self.session.add(anchor)
        anchor.tx_hash = anchor_tx.get("tx_hash") or ""
        anchor.block_height = anchor_tx.get("block_height")
        anchor.block_hash = anchor_tx.get("block_hash")
        anchor.block_proposer = anchor_tx.get("block_proposer")
        ts = anchor_tx.get("timestamp")
        anchor.block_timestamp = ts if isinstance(ts, str) else (datetime.fromtimestamp(ts, UTC).isoformat() if ts else None)
        anchor.registered_at = anchor_tx.get("created_at") or anchor.block_timestamp
        anchor.bound_provider = self._anchor_binding_key(offer, is_gpu)
        anchor.resolved_at = datetime.now(UTC).replace(tzinfo=None)
        return True

    async def _resolve_offer_anchors(
        self,
        offers: list[dict[str, Any]],
        chain_id: str | None,
        local_rows: dict[str, SoftwareService] | None = None,
    ) -> None:
        """Mark offers as confirmed by joining them to sealed anchor txs.

        GPU bundle offers anchor as GPU_REGISTER (payload.gpu_id) and software
        bundle offers as GPU_MARKET (payload.offer_id); the
        state-table endpoints (e.g. /rpc/gpus) do not expose the sealing
        block, so confirmation is derived from the sealed transaction itself.
        Anchors are namespaced per tx type — a GPU_REGISTER seal can never
        confirm a software offer — and bound to the offer's provider, so a tx
        from another sender can't take over or fake an anchor.

        Verified confirmations are stored (SoftwareService.block_* for local
        rows, OfferAnchor otherwise), so a fully-confirmed listing costs no
        chain RPCs; unconfirmed offers are re-probed at most once per
        ``_ANCHOR_NEGATIVE_TTL_SECONDS``. Mutates ``offers`` in place; RPC
        failure degrades to unconfirmed.
        """
        pending = [o for o in offers if not o.get("confirmed")]
        if not pending:
            return
        try:
            # Namespaced keys: the tx-type split applied live applies to
            # stored rows too, so a stored GPU_REGISTER seal can never
            # confirm a software offer.
            wanted: dict[str, tuple[dict[str, Any], bool, str]] = {}
            for offer in pending:
                is_gpu = offer.get("service_type") == "gpu_market"
                raw = offer.get("offer_id") or offer.get("plugin_id")
                if raw:
                    wanted[f"{'gpu' if is_gpu else 'offer'}:{raw}"] = (offer, is_gpu, str(raw))
            if not wanted:
                return

            rows = (
                (
                    await self.session.execute(
                        select(OfferAnchor).where(OfferAnchor.key.in_(list(wanted)))  # type: ignore[attr-defined]
                    )
                )
                .scalars()
                .all()
            )
            stored = {row.key: row for row in rows}
            now = time.monotonic()
            live = self._partition_live_anchors(wanted, stored, now)
            if not live:
                return

            gpu_anchors, offer_anchors = await self._fetch_chain_anchors(chain_id)
            changed = self._apply_chain_anchors(live, gpu_anchors, offer_anchors, now, stored, local_rows)
            if changed:
                await self.session.commit()
        except Exception as e:  # noqa: BLE001 - anchor resolution is best-effort enrichment
            logger.warning("Failed to resolve on-chain offer anchors: %s", e)

    @classmethod
    def _partition_live_anchors(
        cls,
        wanted: dict[str, tuple[dict[str, Any], bool, str]],
        stored: dict[str, OfferAnchor],
        now: float,
    ) -> dict[str, tuple[dict[str, Any], bool, str, str]]:
        """Apply stored OfferAnchor rows to their offers in place and return
        the live set still needing chain resolution, minus entries inside
        the negative-cache TTL."""
        live: dict[str, tuple[dict[str, Any], bool, str, str]] = {}
        for dbkey, (offer, is_gpu, raw) in wanted.items():
            binding = cls._anchor_binding_key(offer, is_gpu)
            row = stored.get(dbkey)
            if row is not None and row.block_height is not None and row.bound_provider and row.bound_provider == binding:
                offer["confirmed"] = True
                offer["tx_hash"] = offer.get("tx_hash") or row.tx_hash or None
                offer["block_height"] = row.block_height
                offer["block_hash"] = offer.get("block_hash") or row.block_hash
                offer["block_proposer"] = offer.get("block_proposer") or row.block_proposer
                if row.block_timestamp and not offer.get("block_timestamp"):
                    offer["block_timestamp"] = row.block_timestamp
                if row.registered_at and not offer.get("registered_at"):
                    offer["registered_at"] = row.registered_at
            else:
                live[dbkey] = (offer, is_gpu, raw, binding)
        cls._evict_anchor_negatives(now)
        return {k: v for k, v in live.items() if cls._anchor_negatives.get((k, v[3]), 0.0) <= now}

    async def _fetch_chain_anchors(
        self, chain_id: str | None
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        """Fetch anchor candidates per key, newest-first, for both anchor tx
        types. Keeping every candidate per key lets a skipped foreign tx
        fall through to the offer's own older anchor instead of shadowing
        it."""
        gpu_anchors: dict[str, list[dict[str, Any]]] = {}
        offer_anchors: dict[str, list[dict[str, Any]]] = {}
        for tx_type, anchors, field in (
            ("GPU_MARKET", offer_anchors, "offer_id"),
            ("GPU_REGISTER", gpu_anchors, "gpu_id"),
        ):
            for tx in await self._rpc_client.query_transactions(transaction_type=tx_type, chain_id=chain_id, limit=1000):
                try:
                    key = (tx.get("payload") or {}).get(field)
                except AttributeError:
                    continue  # malformed tx poisons only itself
                if key:
                    anchors.setdefault(key, []).append(tx)
        return gpu_anchors, offer_anchors

    def _apply_chain_anchors(
        self,
        live: dict[str, tuple[dict[str, Any], bool, str, str]],
        gpu_anchors: dict[str, list[dict[str, Any]]],
        offer_anchors: dict[str, list[dict[str, Any]]],
        now: float,
        stored: dict[str, OfferAnchor],
        local_rows: dict[str, SoftwareService] | None,
    ) -> bool:
        """Resolve each live offer against the fetched chain candidates and
        persist new anchors; returns True when any row was written."""
        changed = False
        for dbkey, (offer, is_gpu, raw, binding) in live.items():
            candidates = (gpu_anchors if is_gpu else offer_anchors).get(raw) or []
            anchor_tx = next(
                (tx for tx in candidates if self._anchor_belongs_to_provider(tx, offer, is_gpu)),
                None,
            )
            if anchor_tx is None:
                self._remember_anchor_negative((dbkey, binding), now + _ANCHOR_NEGATIVE_TTL_SECONDS)
                continue
            ts_str, ts_dt = self._anchor_timestamp(anchor_tx)
            offer["confirmed"] = True
            offer["tx_hash"] = offer.get("tx_hash") or anchor_tx.get("tx_hash")
            offer["block_height"] = anchor_tx.get("block_height")
            offer["block_hash"] = offer.get("block_hash") or anchor_tx.get("block_hash")
            offer["block_proposer"] = offer.get("block_proposer") or anchor_tx.get("block_proposer")
            if ts_str and not offer.get("block_timestamp"):
                offer["block_timestamp"] = ts_str
            if not offer.get("registered_at"):
                offer["registered_at"] = anchor_tx.get("created_at") or offer.get("block_timestamp")
            changed |= self._persist_anchor(dbkey, offer, is_gpu, anchor_tx, ts_dt, stored.get(dbkey), local_rows)
        return changed

    async def get_software_service(self, plugin_id: str) -> dict[str, Any] | None:
        """Get a specific software service (local row or on-chain GPU offer)"""
        from sqlalchemy import select

        from ...domain.market import SoftwareService

        try:
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            data = _local_offer_dict(service) if service else None
            if data is None:
                # GPU bundle offers live only on-chain (GPURegistration state
                # table); fall back so /v1/market/offer/{gpu_id} resolves too.
                try:
                    gpu = await self._rpc_client.get_offer(plugin_id)
                except Exception:  # noqa: BLE001 - chain probe: unreachable RPC means no on-chain offer
                    gpu = None
                if gpu is not None:
                    # Same visibility rule as the list path (#1566): a GPU its
                    # registrant deactivated (or any non-"active" status) must
                    # not resolve as a bookable offer, and a row without a
                    # price cannot be priced — Decimal(str(None)) would 500.
                    gpu_status = gpu.get("status")
                    if (
                        (gpu_status is not None and gpu_status != _GPU_LISTING_DEFAULT_STATUS)
                        or gpu.get("price_per_hour") is None
                        # #1566: open allocations mean the GPU is spoken for —
                        # same visibility rule as the list path.
                        or int(gpu.get("active_allocations") or 0) > 0
                    ):
                        gpu = None
                if gpu:
                    data = _gpu_offer_to_service_dict(gpu, None, settings.hub_rpc_url)
            if data is None:
                return None
            local_rows = {service.plugin_id: service} if service else None
            await self._resolve_offer_anchors([data], None, local_rows)
            return data
        except Exception as e:
            logger.error("Error in get_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def register_software_service(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register or update a software service"""
        try:
            plugin_id = data.get("plugin_id")
            if not plugin_id:
                # The signed message covers plugin_id, so a body without one
                # can never verify — reject plainly instead of deriving a key
                # the client did not sign.
                raise ValueError("plugin_id is required")
            # POST /v1/market/offer is public: the claimed provider_address
            # must prove itself with a fresh, chain-scoped signature before a
            # row is written — otherwise any caller could squat a provider's
            # plugin_id and inherit its anchors.
            data["plugin_id"] = plugin_id
            auth_error, signer = verify_offer_registration(data, settings.default_chain_id or resolve_chain_id())
            if auth_error:
                raise PermissionError(auth_error)
            # Ephemeral proof fields are not service columns.
            for ephemeral in ("signature", "issued_at", "chain_id"):
                data.pop(ephemeral, None)
            # Allow-list, not block-list: only provider-owned fields reach the
            # row. block_*/tx_hash come only from verified anchors, ratings and
            # timestamps only from the server — a signed registration can no
            # longer write its own confirmation or reputation.
            data = {key: value for key, value in data.items() if key in _REGISTRATION_FIELDS}
            existing = await self._upsert_software_service(plugin_id, data, signer)
            return {
                "plugin_id": existing.plugin_id,
                "service_type": existing.service_type,
                "model": existing.model,
                "status": existing.status,
            }
        except PermissionError:
            raise
        except Exception as e:
            logger.error("Error in register_software_service: %s: %s", type(e).__name__, str(e))
            raise

    async def _upsert_software_service(self, plugin_id: str, data: dict[str, Any], signer: str | None) -> SoftwareService:
        """Update the existing row for ``plugin_id`` or create a new one.

        ``data`` must already be allow-listed to ``_REGISTRATION_FIELDS``.
        Raises PermissionError when the signer is not the row's provider.
        """
        from sqlalchemy import select

        from ...domain.market import SoftwareService

        query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()
        if existing:
            # Ownership gate (the GPU_REGISTER check one layer up): a
            # valid signature proves who is asking, not who owns the row.
            # Updating an existing offer requires the row's provider —
            # anyone else's valid signature gets 403, not a takeover.
            if not existing.provider_address:
                raise PermissionError(f"offer {plugin_id} has no provider on record; updates are not permitted")
            if canonical_address(existing.provider_address) != canonical_address(signer or ""):
                raise PermissionError(f"offer {plugin_id} belongs to provider {existing.provider_address}")
            data.pop("provider_address", None)  # ownership never changes via update
            for key, value in data.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await self.session.commit()
            await self.session.refresh(existing)
            logger.info("Updated software service: %s", plugin_id)
        else:
            data["plugin_id"] = plugin_id
            service = SoftwareService(**data)
            self.session.add(service)
            await self.session.commit()
            await self.session.refresh(service)
            existing = service
            logger.info("Registered software service: %s", plugin_id)
        return existing

    async def unregister_software_service(self, plugin_id: str, proof: dict[str, Any]) -> Any:
        """Unregister a software service.

        DELETE /v1/market/offer/{plugin_id} is public, and it used to delete
        any row for any caller; with the same plugin_id free again, anyone
        could register it under their own address and be resolved as the
        provider (the CLI trusts the row's provider_address and endpoint).
        Removal now needs the same proof registration does -- a fresh,
        chain-scoped signature -- scoped by ``action="unregister"`` so a
        captured registration cannot be replayed as a removal, plus the
        ownership gate: the signer must be the row's provider.
        """
        from sqlalchemy import select

        from ...domain.market import SoftwareService

        try:
            data = {
                "plugin_id": plugin_id,
                "provider_address": proof.get("provider_address"),
                "chain_id": proof.get("chain_id"),
                "issued_at": proof.get("issued_at"),
                "signature": proof.get("signature"),
            }
            auth_error, signer = verify_offer_registration(
                data, settings.default_chain_id or resolve_chain_id(), action="unregister"
            )
            if auth_error:
                raise PermissionError(auth_error)
            query = select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)  # type: ignore[arg-type]
            result = await self.session.execute(query)
            service = result.scalar_one_or_none()
            if not service:
                # Raise rather than return an HTTP-shaped tuple: this is the service layer,
                # and the tuple was serialized by FastAPI as a 200 with the status buried in
                # a JSON array. Matches list_offers/update_offer_status above.
                raise ValueError(f"Service not found: {plugin_id}")
            if not service.provider_address:
                raise PermissionError(f"offer {plugin_id} has no provider on record; removal is not permitted")
            if canonical_address(service.provider_address) != canonical_address(signer or ""):
                raise PermissionError(f"offer {plugin_id} belongs to provider {service.provider_address}")
            await self.session.delete(service)
            await self.session.commit()
            logger.info("Unregistered software service: %s", plugin_id)
            return {"plugin_id": plugin_id, "status": "unregistered"}
        except PermissionError:
            raise
        except Exception as e:
            logger.error("Error in unregister_software_service: %s: %s", type(e).__name__, str(e))
            raise
