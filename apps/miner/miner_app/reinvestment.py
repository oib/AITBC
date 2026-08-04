"""Autonomous provider reinvestment loop for OpenClaw economics.

ponytail: This is a skeleton engine that converts earned AITBC into on-chain
actions for staking and capacity reinvestment. It uses the shared
`aitbc.agent_economics` primitives so it wires directly to the economic types
Agent A owns. Real execution will be handled by an on-chain worker; this module
only produces validated action payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from aitbc.agent_economics import Budget, OnChainAction, OnChainActionType, RevenueRoute


@dataclass
class ReinvestmentPolicy:
    """Constraints governing how a provider reinvests earnings.

    - reinvest_pct: total percentage of earnings to reinvest (0-100)
    - staking_pct: portion of the reinvested amount that goes to staking (0-100)
    - capacity_reserve_pct: portion kept for future GPU/storage purchases
    - min_reinvest_amount: earnings below this are held, not reinvested
    """

    reinvest_pct: Decimal = Decimal("50")
    staking_pct: Decimal = Decimal("60")
    capacity_reserve_pct: Decimal = Decimal("40")
    min_reinvest_amount: Decimal = Decimal("0.01")
    chain_id: str = "ait-hub"
    staking_contract: str = ""
    reserve_address: str = ""

    def __post_init__(self) -> None:
        for name in ("reinvest_pct", "staking_pct", "capacity_reserve_pct"):
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, Decimal(value))
            value = getattr(self, name)
            if not (Decimal("0") <= value <= Decimal("100")):
                raise ValueError(f"{name} must be between 0 and 100")
        if self.staking_pct + self.capacity_reserve_pct != Decimal("100"):
            raise ValueError("staking_pct + capacity_reserve_pct must equal 100")


class ReinvestmentEngine:
    """Convert provider earnings into staking and capacity-reserve actions."""

    def __init__(self, budget: Budget, policy: ReinvestmentPolicy) -> None:
        self.budget = budget
        self.policy = policy

    def plan_reinvestment(self, earnings: Decimal | float | int | str, agent_id: str) -> list[OnChainAction]:
        """Return the on-chain actions produced from a batch of earnings.

        ponytail: No actual blockchain execution happens here; the engine only
        validates affordability and returns action payloads.
        """
        if not isinstance(earnings, Decimal):
            earnings = Decimal(str(earnings))
        if earnings <= 0:
            return []

        reinvest_amount = earnings * self.policy.reinvest_pct / Decimal("100")
        if reinvest_amount < self.policy.min_reinvest_amount:
            return []

        # Ensure the budget can cover the planned reinvestment.
        if reinvest_amount > self.budget.available:
            raise ValueError("reinvestment amount exceeds available budget")

        stake_amount = reinvest_amount * self.policy.staking_pct / Decimal("100")
        reserve_amount = reinvest_amount - stake_amount

        actions: list[OnChainAction] = []
        if stake_amount > 0 and self.policy.staking_contract:
            actions.append(
                OnChainAction(
                    action_id=f"stake-{uuid4().hex[:8]}",
                    agent_id=agent_id,
                    action_type=OnChainActionType.STAKE,
                    chain_id=self.policy.chain_id,
                    contract_address=self.policy.staking_contract,
                    amount=stake_amount,
                    payload={"source_budget_id": self.budget.budget_id},
                )
            )
        if reserve_amount > 0 and self.policy.reserve_address:
            actions.append(
                OnChainAction(
                    action_id=f"reserve-{uuid4().hex[:8]}",
                    agent_id=agent_id,
                    action_type=OnChainActionType.TRANSFER,
                    chain_id=self.policy.chain_id,
                    contract_address=self.policy.reserve_address,
                    amount=reserve_amount,
                    payload={"purpose": "capacity_reserve"},
                )
            )
        return actions

    def apply(self, earnings: Decimal | float | int | str, agent_id: str) -> list[OnChainAction]:
        """Plan reinvestment, allocate budget, and return actions for execution."""
        actions = self.plan_reinvestment(earnings, agent_id)
        total = sum((action.amount for action in actions), start=Decimal("0"))
        if total > 0:
            self.budget.allocate(total)
        return actions


def build_revenue_route(agent_id: str, recipient: str, percentage: Decimal) -> RevenueRoute:
    """Convenience helper to build a revenue route for a provider."""
    return RevenueRoute(
        route_id=f"route-{uuid4().hex[:8]}",
        route_type="provider",
        recipient=recipient,
        percentage=percentage,
        chain_id="ait-hub",
        meta={"agent_id": agent_id},
    )
