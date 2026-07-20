"""Global service state for the Trading Service.

Singletons are initialized lazily on first request (or warmed by lifespan).
Lifespan should call ``set_gossip_client`` / ``set_lease_tracker`` before
any request is served when startup succeeds.
"""

from typing import Any

from aitbc.trading.offer_types import OfferDiscoveryResult, OfferSyncStatusEntry

from .config import settings
from .services.gossip_client import GossipClient
from .services.lease_tracker import OfferLeaseTracker
from .services.offer_notification_service import OfferNotificationService
from .services.offer_search_service import OfferSearchService
from .services.offer_subscription_service import OfferSubscriptionService
from .services.offer_sync_service import OfferSyncService
from .storage import get_session


_subscription_service: OfferSubscriptionService | None = None
_notification_service: OfferNotificationService | None = None
_search_service: OfferSearchService | None = None
_gossip_client: Any = None
_lease_tracker: Any = None


class _PollingSyncWrapper:
    """Lightweight wrapper for B20 polling fallback.

    Creates an :class:`OfferSyncService` with a fresh DB session on each
    ``sync_chain`` call, then closes the session.  This avoids holding a
    long-lived session in the global subscription service.
    """

    async def sync_chain(self, chain_id: str) -> dict[str, Any]:
        async with get_session() as session:
            svc = OfferSyncService(session)
            return await svc.sync_chain(chain_id)


def _synced_offer_to_dict(offer: Any) -> dict[str, Any]:
    """Convert a SyncedOffer to a dict for JSON response."""
    return offer.to_dict() if hasattr(offer, "to_dict") else dict(offer)


def _discovery_result_to_dict(result: OfferDiscoveryResult) -> dict[str, Any]:
    """Convert an OfferDiscoveryResult to a dict for JSON response."""
    return {
        "offers": [_synced_offer_to_dict(o) for o in result.offers],
        "total_count": result.total_count,
        "chains_searched": result.chains_searched,
        "stale_count": result.stale_count,
        "sync_triggered": result.sync_triggered,
    }


def _status_entry_to_dict(entry: OfferSyncStatusEntry) -> dict[str, Any]:
    """Convert an OfferSyncStatusEntry to a dict for JSON response."""
    return {
        "chain_id": entry.chain_id,
        "last_sync": entry.last_sync,
        "offer_count": entry.offer_count,
        "stale_count": entry.stale_count,
        "error_count": entry.error_count,
        "is_syncing": entry.is_syncing,
    }


def set_gossip_client(client: Any) -> None:
    """Set the global gossip client (called from lifespan)."""
    global _gossip_client
    _gossip_client = client


def set_lease_tracker(tracker: Any) -> None:
    """Set the global lease tracker (called from lifespan)."""
    global _lease_tracker
    _lease_tracker = tracker


def get_subscription_service() -> OfferSubscriptionService:
    """Get or create the global OfferSubscriptionService."""
    global _subscription_service
    if _subscription_service is None:
        # B18: Use the gossip client initialized on startup (or create a fallback)
        gossip = _gossip_client or GossipClient(
            backend=settings.gossip_backend,
            redis_url=settings.gossip_broadcast_url,
        )
        # B19: Use the lease tracker initialized on startup (or create a fallback)
        tracker = _lease_tracker or OfferLeaseTracker(redis_url=settings.lease_tracker_redis_url)

        # B20: Factory that creates an OfferSyncService for polling fallback
        def _sync_factory() -> _PollingSyncWrapper:
            return _PollingSyncWrapper()

        _subscription_service = OfferSubscriptionService(
            gossip_client=gossip,
            lease_tracker=tracker,
            offer_sync_factory=_sync_factory,
        )
    return _subscription_service


def get_notification_service() -> OfferNotificationService:
    """Get or create the global OfferNotificationService."""
    global _notification_service
    if _notification_service is None:
        _notification_service = OfferNotificationService(debounce_ms=settings.offer_subscription_debounce_ms)
    return _notification_service


def get_search_service() -> OfferSearchService:
    """Get or create the global OfferSearchService."""
    global _search_service
    if _search_service is None:
        _search_service = OfferSearchService()
    return _search_service


async def shutdown() -> None:
    """Stop global gossip client and lease tracker (called from lifespan)."""
    global _gossip_client, _lease_tracker
    if _gossip_client is not None:
        try:
            await _gossip_client.stop()
        except Exception:
            pass
        _gossip_client = None
    if _lease_tracker is not None:
        try:
            await _lease_tracker.stop()
        except Exception:
            pass
        _lease_tracker = None
