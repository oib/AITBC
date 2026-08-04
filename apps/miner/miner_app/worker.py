"""Background worker that turns provider earnings into reinvestment actions."""

from __future__ import annotations

import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from aitbc.agent_economics import Budget, OnChainActionType

from .reinvestment import ReinvestmentEngine, ReinvestmentPolicy


def _publish_capacity_for_agent(agent_id: str, actions: list[Any]) -> None:
    """Best-effort capacity publish after a reinvestment action.

    ponytail: If the GPU app publisher is not importable (e.g. not on PYTHONPATH)
    the publish is skipped silently. Production should wire a real publisher.
    """
    try:
        from gpu_app.capacity_publisher import publish_capacity
    except ImportError:
        return

    capacity = sum(1 for a in actions if getattr(a, "action_type", None) == OnChainActionType.STAKE)
    if capacity:
        publish_capacity(agent_id, capacity)


class ReinvestmentWorker:
    """Poll a provider's earnings and dispatch reinvestment actions.

    ponytail: This is a skeleton worker. A production implementation will plug
    in a real earnings source (blockchain events, marketplace payouts) and an
    on-chain transaction dispatcher.
    """

    def __init__(
        self,
        engine: ReinvestmentEngine,
        agent_id: str,
        earnings_source: Callable[[], Decimal] | None = None,
        dispatcher: Callable[[list[Any]], None] | None = None,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self.engine = engine
        self.agent_id = agent_id
        self.earnings_source = earnings_source or self._default_earnings
        self.dispatcher = dispatcher or self._default_dispatcher
        self.poll_interval_seconds = poll_interval_seconds
        self._running = False

    @staticmethod
    def _default_earnings() -> Decimal:
        """No-op earnings source — always returns zero."""
        return Decimal("0")

    @staticmethod
    def _default_dispatcher(actions: list[Any]) -> None:
        """No-op dispatcher for skeleton mode."""
        pass

    def run_once(self) -> list[Any]:
        """Fetch one batch of earnings, plan actions, and dispatch them."""
        earnings = self.earnings_source()
        actions = self.engine.apply(earnings, self.agent_id)
        if actions:
            self.dispatcher(actions)
            _publish_capacity_for_agent(self.agent_id, actions)
        return actions

    def run(self) -> None:
        """Run the worker loop until ``stop()`` is called."""
        self._running = True
        while self._running:
            self.run_once()
            time.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        """Signal the worker loop to stop."""
        self._running = False


def build_worker(
    budget: Budget,
    agent_id: str,
    policy: ReinvestmentPolicy | None = None,
    **kwargs: Any,
) -> ReinvestmentWorker:
    """Factory helper for the common reinvestment worker setup."""
    policy = policy or ReinvestmentPolicy()
    engine = ReinvestmentEngine(budget, policy)
    return ReinvestmentWorker(engine=engine, agent_id=agent_id, **kwargs)
