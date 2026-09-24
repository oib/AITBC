"""
Portfolio Aggregation Service
Aggregates portfolio data from wallet, exchange, market, trading, and AI services
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


from aitbc.aitbc_logging import get_logger
from aitbc.http_client import RequestIDPropagatingClient
from aitbc.utils.units import units_to_ait

logger = get_logger(__name__)


class PortfolioAggregationService:
    """Service to aggregate portfolio data from multiple AITBC services"""

    def __init__(self) -> None:
        # Service URLs follow the api-gateway convention: env override, loopback default.
        self.wallet_service_url = os.getenv("WALLET_SERVICE_URL", "http://localhost:8108")
        self.exchange_service_url = os.getenv("EXCHANGE_SERVICE_URL", "http://localhost:8106")
        self.market_service_url = os.getenv("MARKET_SERVICE_URL", "http://localhost:8102")
        self.trading_service_url = os.getenv("TRADING_SERVICE_URL", "http://localhost:8104")
        self.ai_service_url = os.getenv("AI_SERVICE_URL", "http://localhost:8005")
        # Wallet admin routes (/v1/wallets) require X-API-Key = WALLET_API_KEY,
        # with COORDINATOR_API_KEY as the documented shared fallback.
        self._wallet_api_key = os.getenv("WALLET_API_KEY") or os.getenv("COORDINATOR_API_KEY") or ""
        # The AI engine expects ``Authorization: Bearer $AI_ENGINE_API_KEY``
        # (ai-engine/src/ai_service.py verify_auth).
        self._ai_api_key = os.getenv("AI_ENGINE_API_KEY") or ""
        # Trading routes sit behind X-Trading-Api-Key = TRADING_API_KEY
        # (trading_service/dependencies.py require_trading_api_key).
        self._trading_api_key = os.getenv("TRADING_API_KEY") or ""
        self.http_client = RequestIDPropagatingClient(timeout=10.0)

    async def get_unified_portfolio(self, agent_address: str | None = None) -> dict[str, Any]:
        """
        Get unified portfolio view by aggregating data from all services

        Args:
            agent_address: Optional agent address to filter portfolio data

        Returns:
            Unified portfolio data containing wallet balances, exchange rates,
            market stats, trading analytics, and AI signals
        """
        try:
            wallet_data = await self._get_wallet_balances(agent_address)
            exchange_data = await self._get_exchange_rates()
            market_data = await self._get_market_stats()
            trading_data = await self._get_trading_analytics(agent_address)
            ai_data = await self._get_ai_trade_signals()
            portfolio_summary = self._calculate_portfolio_summary(
                wallet_data, exchange_data, market_data, trading_data, ai_data
            )
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "agent_address": agent_address,
                "wallet": wallet_data,
                "exchange": exchange_data,
                "market": market_data,
                "trading": trading_data,
                "ai_signals": ai_data,
                "summary": portfolio_summary,
            }
        except Exception as e:
            logger.error("Error aggregating portfolio data: %s", str(e))
            raise

    async def _get_wallet_balances(self, agent_address: str | None = None) -> dict[str, Any]:
        """Fetch wallet balances from wallet service"""
        try:
            response = await self.http_client.get(
                f"{self.wallet_service_url}/v1/wallets",
                headers={"X-API-Key": self._wallet_api_key} if self._wallet_api_key else None,
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as e:
                    logger.warning("Failed to parse wallet data: %s", e)
                    return {"wallets": [], "total_wallets": 0, "total_balance": 0, "error": str(e)}
                wallets = data.get("items", [])
                if agent_address:
                    wallets = [w for w in wallets if w.get("public_key") == agent_address or w.get("address") == agent_address]
                # Wallet descriptors carry no balance — fetch each wallet's
                # balance from the wallet service (bounded by wallet count).
                total_units = 0
                for w in wallets:
                    wallet_id = w.get("wallet_id")
                    if not wallet_id:
                        continue
                    try:
                        bal_resp = await self.http_client.get(
                            f"{self.wallet_service_url}/v1/wallets/{wallet_id}/balance",
                            headers={"X-API-Key": self._wallet_api_key} if self._wallet_api_key else None,
                        )
                        if bal_resp.status_code == 200:
                            total_units += int(bal_resp.json().get("balance", 0) or 0)
                    except Exception as e:
                        logger.warning("Failed to fetch balance for wallet %s: %s", wallet_id, e)
                total_balance = units_to_ait(total_units)
                return {"wallets": wallets, "total_wallets": len(wallets), "total_balance": total_balance}
            else:
                logger.warning("Wallet service returned status %s", response.status_code)
                return {"wallets": [], "total_wallets": 0, "total_balance": 0, "error": "Wallet service unavailable"}
        except Exception as e:
            logger.error("Error fetching wallet balances: %s", str(e))
            return {"wallets": [], "total_wallets": 0, "total_balance": 0, "error": str(e)}

    async def _get_exchange_rates(self) -> dict[str, Any]:
        """Fetch exchange rates from exchange service"""
        try:
            response = await self.http_client.get(f"{self.exchange_service_url}/v1/cross-chain/rates")
            if response.status_code == 200:
                try:
                    return dict(response.json())
                except Exception as e:
                    logger.warning("Failed to parse exchange rates: %s", e)
                    return {"rates": {}, "error": str(e)}
            else:
                logger.warning("Exchange service returned status %s", response.status_code)
                return {"rates": {}, "error": "Exchange service unavailable"}
        except Exception as e:
            logger.error("Error fetching exchange rates: %s", str(e))
            return {"rates": {}, "error": str(e)}

    async def _get_market_stats(self) -> dict[str, Any]:
        """Fetch market statistics from market service"""
        try:
            response = await self.http_client.get(f"{self.market_service_url}/v1/market/analytics?period_type=daily")
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as e:
                    logger.warning("Failed to parse market stats: %s", e)
                    return {"offers": 0, "bids": 0, "capacity": 0, "error": str(e)}
                return {
                    "offers": data.get("total_offers", 0),
                    "capacity": data.get("total_capacity", 0),
                    "average_price": data.get("average_price", 0),
                    "period_type": data.get("period_type"),
                }
            else:
                logger.warning("Market service returned status %s", response.status_code)
                return {"offers": 0, "capacity": 0, "error": "Market service unavailable"}
        except Exception as e:
            logger.error("Error fetching market stats: %s", str(e))
            return {"offers": 0, "capacity": 0, "error": str(e)}

    async def _get_trading_analytics(self, agent_address: str | None = None) -> dict[str, Any]:
        """Fetch trading analytics from trading service.

        ``GET /v1/trading/analytics`` accepts only ``period_type``; there is no
        per-agent filter, so ``agent_address`` is accepted for signature
        compatibility and ignored.
        """
        try:
            response = await self.http_client.get(
                f"{self.trading_service_url}/v1/trading/analytics",
                headers={"X-Trading-Api-Key": self._trading_api_key} if self._trading_api_key else None,
            )
            if response.status_code == 200:
                try:
                    return dict(response.json())
                except Exception as e:
                    logger.warning("Failed to parse trading analytics: %s", e)
                    return {"error": str(e)}
            else:
                logger.warning("Trading service returned status %s", response.status_code)
                return {"error": "Trading service unavailable"}
        except Exception as e:
            logger.error("Error fetching trading analytics: %s", str(e))
            return {"error": str(e)}

    async def _get_ai_trade_signals(self) -> dict[str, Any]:
        """Fetch AI trade signals from AI service.

        The AI engine is a simulation placeholder — it only answers when the
        operator sets ``AI_ENGINE_ALLOW_SIMULATION=true``, and its payload is
        labelled ``simulated: true``. We propagate that label verbatim so the
        aggregate cannot launder fabricated signals as real ones.
        """
        try:
            response = await self.http_client.post(
                f"{self.ai_service_url}/api/ai/trade",
                json={"symbol": "AITBC/ETH", "strategy": "ai_enhanced"},
                headers={"Authorization": f"Bearer {self._ai_api_key}"} if self._ai_api_key else None,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and "decision" in data:
                    decision = data["decision"]
                    return {
                        "simulated": bool(data.get("simulated", False)),
                        "notice": data.get("notice"),
                        "signals": [
                            {
                                "symbol": decision.get("symbol"),
                                "signal": decision.get("signal"),
                                "confidence": decision.get("confidence"),
                                "price": decision.get("price"),
                                "reasoning": decision.get("reasoning"),
                                "timestamp": decision.get("timestamp"),
                            }
                        ],
                    }
                else:
                    return {"signals": [], "error": data.get("message") or "Invalid response format"}
            else:
                logger.warning("AI service returned status %s", response.status_code)
                return {"signals": [], "error": "AI service unavailable"}
        except Exception as e:
            logger.error("Error fetching AI signals: %s", str(e))
            return {"signals": [], "error": str(e)}

    def _calculate_portfolio_summary(
        self,
        wallet_data: dict[str, Any],
        exchange_data: dict[str, Any],
        market_data: dict[str, Any],
        trading_data: dict[str, Any],
        ai_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Calculate portfolio summary metrics from aggregated data"""
        try:
            total_aitbc_balance = 0.0
            wallets = wallet_data.get("wallets", [])
            total_aitbc_balance = wallet_data.get("total_balance", len(wallets))
            rates = exchange_data.get("rates", {})
            # Exchange returns flat {"AITBC::ETH": <float>} — AITBC priced in ETH.
            # When the exchange is unreachable there is no rate: report nulls
            # rather than pricing the balance off a hardcoded fallback.
            aitbc_eth_rate = Decimal(str(rates["AITBC::ETH"])) if rates.get("AITBC::ETH") is not None else None
            eth_value = total_aitbc_balance * aitbc_eth_rate if aitbc_eth_rate is not None else None
            market_offers = market_data.get("offers", 0)
            market_capacity = market_data.get("capacity", 0)
            # Trading analytics puts the counters at top level.
            total_trades = trading_data.get("total_trades", 0)
            completed_trades = trading_data.get("completed_trades", 0)
            success_rate = completed_trades / total_trades * 100 if total_trades > 0 else 0
            signals = ai_data.get("signals", [])
            avg_signal_confidence = 0.0
            if signals:
                avg_signal_confidence = sum(s.get("confidence", 0) for s in signals) / len(signals)
            return {
                "total_aitbc_balance": total_aitbc_balance,
                "eth_equivalent": eth_value,
                "exchange_rate": aitbc_eth_rate,
                "market_exposure": {
                    "offers": market_offers,
                    "capacity": market_capacity,
                },
                "trading_performance": {
                    "total_trades": total_trades,
                    "completed_trades": completed_trades,
                    "success_rate": success_rate,
                },
                "ai_signal_summary": {
                    "total_signals": len(signals),
                    "average_confidence": avg_signal_confidence,
                    "simulated": bool(ai_data.get("simulated", False)),
                },
            }
        except Exception as e:
            logger.error("Error calculating portfolio summary: %s", str(e))
            return {"total_aitbc_balance": 0, "eth_equivalent": 0, "exchange_rate": 0, "error": str(e)}

    async def close(self) -> None:
        """Close HTTP client"""
        await self.http_client.aclose()
