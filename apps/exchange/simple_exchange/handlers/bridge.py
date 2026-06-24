"""Bridge deposit, status, price, and estimate handlers."""

import os
import urllib.parse


class BridgeMixin:
    """Cross-chain bridge methods."""

    def handle_bridge_price(self, parsed):
        """GET /v1/bridge/price?base=ETH&quote=USD — oracle price feed"""
        import sys

        sys.path.insert(0, "/opt/aitbc")
        params = urllib.parse.parse_qs(parsed.query)
        base = params.get("base", ["ETH"])[0].upper()
        quote = params.get("quote", ["USD"])[0].upper()
        try:
            from aitbc.oracles.price_oracle import get_price_oracle

            result = get_price_oracle().get_price(base, quote)
            if result:
                self.send_json_response(
                    {
                        "pair": f"{result.base}/{result.quote}",
                        "price": result.price,
                        "source": result.source,
                        "timestamp": result.timestamp,
                    }
                )
            else:
                self.send_json_response({"error": f"No price available for {base}/{quote}"}, status=404)
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_bridge_status(self, tx_id):
        """GET /v1/bridge/status[/{tx_id}]"""
        bridge_addr = os.getenv("BRIDGE_CONTRACT_ADDRESS")
        if tx_id:
            self.send_json_response(
                {"tx_id": tx_id, "status": "pending", "message": "Bridge contract not yet deployed on-chain"}
            )
        else:
            if bridge_addr:
                status = "deployed"
                msg = "Bridge contract deployed on-chain"
            else:
                status = "configured"
                msg = "Deploy bridge contract with: npx hardhat run contracts/scripts/deploy-bridge.js --network sepolia"
            deposit_addr = os.getenv("BRIDGE_ETH_ADDRESS")
            self.send_json_response(
                {
                    "bridge": "CrossChainBridge",
                    "status": status,
                    "direction": "ETH → AIT (deposits only)",
                    "supported_chains": ["ethereum", "aitbc"],
                    "deposit_address": deposit_addr,
                    "withdraw_address": None,
                    "withdraw_enabled": False,
                    "fee_rate": 0.005,
                    "contract_address": bridge_addr,
                    "message": msg,
                    "note": "Withdrawals (AIT → ETH) are currently disabled. Only ETH deposits to AIT are supported.",
                }
            )

    def handle_bridge_deposit(self):
        """POST /v1/bridge/deposit — initiate ETH→AIT bridge deposit"""
        if not self._require_api_key():
            return
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            body = self._read_json_body()
            eth_amount = float(body.get("eth_amount", 0))
            ait_address = body.get("ait_address", "")

            if not eth_amount or not ait_address:
                self.send_json_response({"error": "eth_amount and ait_address required"}, status=400)
                return

            # Get bridge configuration
            bridge_eth_address = os.getenv("BRIDGE_ETH_ADDRESS")
            min_eth_deposit = float(os.getenv("MIN_ETH_DEPOSIT", "0.001"))
            eth_network = os.getenv("ETH_NETWORK", "sepolia")

            if not bridge_eth_address:
                self.send_json_response({"error": "Bridge not configured - BRIDGE_ETH_ADDRESS not set"}, status=500)
                return

            # Validate minimum deposit
            if eth_amount < min_eth_deposit:
                self.send_json_response(
                    {"error": f"Minimum deposit is {min_eth_deposit} ETH", "min_deposit": min_eth_deposit}, status=400
                )
                return

            # Get prices for estimate
            oracle = get_price_oracle()
            eth_usd = oracle.get_price("ETH", "USD")
            ait_usd = oracle.get_price("AIT", "USD")

            # Calculate AIT amount
            ait_amount = None
            if eth_usd and ait_usd and ait_usd.price > 0:
                ait_amount = (eth_amount * eth_usd.price) / ait_usd.price

            # Calculate fee (0.5%)
            fee_eth = eth_amount * 0.005
            net_eth = eth_amount - fee_eth

            # Hex-encode the AIT address as UTF-8 for the tx data field
            # (matches what bridge_monitor.parse_ait_recipient decodes)
            transaction_data_hex = "0x" + ait_address.encode("utf-8").hex()

            self.send_json_response(
                {
                    "status": "ready",
                    "message": "Send ETH to the bridge address with your AIT address in transaction data",
                    "instructions": {
                        "send_eth_to": bridge_eth_address,
                        "network": eth_network,
                        "amount_eth": eth_amount,
                        "transaction_data": ait_address,
                        "transaction_data_hex": transaction_data_hex,
                        "min_deposit": min_eth_deposit,
                    },
                    "estimate": {
                        "eth_amount": eth_amount,
                        "fee_eth": round(fee_eth, 8),
                        "net_eth": round(net_eth, 8),
                        "estimated_ait_amount": round(ait_amount, 6) if ait_amount else None,
                        "eth_usd_price": eth_usd.price if eth_usd else None,
                        "ait_usd_price": ait_usd.price if ait_usd else None,
                        "ait_recipient": ait_address,
                    },
                },
                status=200,
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_bridge_withdraw(self):
        """POST /v1/bridge/withdraw — initiate AIT→ETH bridge withdrawal (DISABLED)"""
        if not self._require_api_key():
            return
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")

            body = self._read_json_body()
            ait_amount = float(body.get("ait_amount", 0))
            eth_address = body.get("eth_address", "")

            if not ait_amount or not eth_address:
                self.send_json_response({"error": "ait_amount and eth_address required"}, status=400)
                return

            # Feature is disabled
            self.send_json_response(
                {
                    "status": "disabled",
                    "message": "AIT→ETH withdrawals are currently disabled. Only ETH→AIT deposits are supported.",
                    "reason": "Withdrawal functionality not yet enabled",
                    "supported_direction": "ETH → AIT (deposits only)",
                    "deposit_endpoint": "/v1/bridge/deposit",
                },
                status=503,
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_bridge_deposits(self, parsed):
        """GET /v1/bridge/deposits — list bridge deposits"""
        try:
            import sys
            from urllib.parse import parse_qs

            sys.path.insert(0, "/opt/aitbc/apps/bridge-monitor/src")
            from bridge_monitor.storage import BridgeDepositStatus, count_deposits, get_deposits

            params = parse_qs(parsed.query)
            status_filter = params.get("status", [None])[0]
            limit = int(params.get("limit", [50])[0])
            offset = int(params.get("offset", [0])[0])

            status = None
            if status_filter:
                try:
                    status = BridgeDepositStatus(status_filter)
                except ValueError:
                    self.send_json_response({"error": f"Invalid status: {status_filter}"}, status=400)
                    return

            deposits = get_deposits(status=status, limit=limit, offset=offset)
            total = count_deposits(status=status)

            # Convert sqlite3.Row objects to dicts if needed
            deposits_list = []
            for d in deposits:
                if isinstance(d, dict):
                    deposits_list.append(d)
                else:
                    # sqlite3.Row object
                    deposits_list.append(dict(d))

            self.send_json_response(
                {
                    "deposits": deposits_list,
                    "count": len(deposits_list),
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_bridge_deposit_detail(self, tx_hash):
        """GET /v1/bridge/deposit/{tx_hash} — get deposit details"""
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc/apps/bridge-monitor/src")
            from bridge_monitor.storage import get_deposit

            deposit = get_deposit(tx_hash)
            if not deposit:
                self.send_json_response({"error": "Deposit not found"}, status=404)
                return

            self.send_json_response(deposit)
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_bridge_estimate(self):
        """POST /v1/bridge/estimate — estimate AIT amount for ETH"""
        if not self._require_api_key():
            return
        try:
            body = self._read_json_body()
            eth_amount = float(body.get("eth_amount", 0))

            if eth_amount <= 0:
                self.send_json_response({"error": "eth_amount must be positive"}, status=400)
                return

            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            eth_usd_result = oracle.get_price("ETH", "USD")
            ait_usd_result = oracle.get_price("AIT", "USD")

            if not eth_usd_result or not ait_usd_result:
                self.send_json_response({"error": "Cannot get oracle prices"}, status=503)
                return

            eth_usd = eth_usd_result.price
            ait_usd = ait_usd_result.price

            if ait_usd == 0:
                self.send_json_response({"error": "AIT/USD price is zero"}, status=503)
                return

            ait_amount = (eth_amount * eth_usd) / ait_usd

            self.send_json_response(
                {
                    "eth_amount": eth_amount,
                    "eth_usd_price": eth_usd,
                    "ait_usd_price": ait_usd,
                    "ait_amount": round(ait_amount, 6),
                    "exchange_rate": round(ait_amount / eth_amount, 2),
                }
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)
