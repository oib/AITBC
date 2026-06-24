#!/usr/bin/env python3
"""
AITBC Trading Agent
Automated trading agent for AITBC marketplace
"""

import asyncio
from typing import Any

from aitbc.agent_bridge.src.integration_layer import AgentServiceBridge

from aitbc import get_logger

logger = get_logger(__name__)


class TradingAgent:
    """Automated trading agent"""

    def __init__(self, agent_id: str, config: dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.bridge = AgentServiceBridge()
        self.is_running = False
        self.trading_strategy = config.get("strategy", "basic")
        self.symbols = config.get("symbols", ["AITBC/BTC"])
        self.trade_interval = config.get("trade_interval", 60)  # seconds

    async def start(self) -> bool:
        """Start trading agent"""
        try:
            # Register with service bridge
            success = await self.bridge.start_agent(
                self.agent_id,
                {
                    "type": "trading",
                    "capabilities": ["market_analysis", "trading", "risk_management"],
                    "endpoint": "http://localhost:8005",
                },
            )

            if success:
                self.is_running = True
                logger.info("Trading agent %s started successfully", self.agent_id)
                return True
            else:
                logger.warning("Failed to start trading agent %s", self.agent_id)
                return False
        except Exception as e:
            logger.error("Error starting trading agent: %s", e)
            return False

    async def stop(self) -> bool:
        """Stop trading agent"""
        self.is_running = False
        success = await self.bridge.stop_agent(self.agent_id)
        if success:
            logger.info("Trading agent %s stopped successfully", self.agent_id)
        return bool(success)

    async def run_trading_loop(self):
        """Main trading loop"""
        while self.is_running:
            try:
                for symbol in self.symbols:
                    await self._analyze_and_trade(symbol)

                await asyncio.sleep(self.trade_interval)
            except Exception as e:
                logger.error("Error in trading loop: %s", e)
                await asyncio.sleep(10)  # Wait before retrying

    async def _analyze_and_trade(self, symbol: str) -> None:
        """Analyze market and execute trades"""
        try:
            # Perform market analysis
            analysis_task = {"type": "market_analysis", "symbol": symbol, "strategy": self.trading_strategy}

            analysis_result = await self.bridge.execute_agent_task(self.agent_id, analysis_task)

            if analysis_result.get("status") == "success":
                analysis = analysis_result["result"]["analysis"]

                # Make trading decision
                if self._should_trade(analysis):
                    await self._execute_trade(symbol, analysis)
            else:
                logger.warning("Market analysis failed for %s: %s", symbol, analysis_result)

        except Exception as e:
            logger.error("Error in analyze_and_trade for %s: %s", symbol, e)

    def _should_trade(self, analysis: dict[str, Any]) -> bool:
        """Determine if should execute trade"""
        recommendation = analysis.get("recommendation", "hold")
        return recommendation in ["buy", "sell"]

    async def _execute_trade(self, symbol: str, analysis: dict[str, Any]) -> None:
        """Execute trade based on analysis"""
        try:
            recommendation = analysis.get("recommendation", "hold")

            if recommendation == "buy":
                trade_task = {
                    "type": "trading",
                    "symbol": symbol,
                    "side": "buy",
                    "amount": self.config.get("trade_amount", 0.1),
                    "strategy": self.trading_strategy,
                }
            elif recommendation == "sell":
                trade_task = {
                    "type": "trading",
                    "symbol": symbol,
                    "side": "sell",
                    "amount": self.config.get("trade_amount", 0.1),
                    "strategy": self.trading_strategy,
                }
            else:
                return

            trade_result = await self.bridge.execute_agent_task(self.agent_id, trade_task)

            if trade_result.get("status") == "success":
                logger.info("Trade executed successfully: %s", trade_result)
            else:
                logger.warning("Trade execution failed: %s", trade_result)

        except Exception as e:
            logger.error("Error executing trade: %s", e)

    async def get_status(self) -> dict[str, Any]:
        """Get agent status"""
        result = await self.bridge.get_agent_status(self.agent_id)
        return dict(result) if isinstance(result, dict) else {"status": "unknown"}


# Main execution
async def main():
    """Main trading agent execution"""
    agent_id = "trading-agent-001"
    config = {"strategy": "basic", "symbols": ["AITBC/BTC"], "trade_interval": 30, "trade_amount": 0.1}

    agent = TradingAgent(agent_id, config)

    # Start agent
    if await agent.start():
        try:
            # Run trading loop
            await agent.run_trading_loop()
        except KeyboardInterrupt:
            logger.info("Shutting down trading agent...")
        finally:
            await agent.stop()
    else:
        logger.error("Failed to start trading agent")


if __name__ == "__main__":
    asyncio.run(main())
