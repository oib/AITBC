"""Bridge deposit, status, price, and estimate handlers."""

import urllib.parse
from decimal import Decimal

from aitbc.utils.decimal import to_decimal as _to_decimal
from ..config import bridge_config


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
                self.send_json_response(  # type: ignore[attr-defined]
                    {
                        "pair": f"{result.base}/{result.quote}",
                        "price": result.price,
                        "source": result.source,
                        "timestamp": result.timestamp,
                    }
                )
            else:
                self.send_json_response({"error": f"No price available for {base}/{quote}"}, status=404)  # type: ignore[attr-defined]
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]

    def handle_bridge_status(self, tx_id):
        """GET /v1/bridge/status[/{tx_id}]"""
        if tx_id:
            self.send_json_response(  # type: ignore[attr-defined]
                {"tx_id": tx_id, "status": "pending", "message": "Bridge contract not yet deployed on-chain"}
            )
        else:
            self.send_json_response(bridge_config.as_status())  # type: ignore[attr-defined]

    def handle_bridge_deposit(self):
        """POST /v1/bridge/deposit — initiate ETH→AIT bridge deposit"""
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            body = self._read_json_body()  # type: ignore[attr-defined]
            try:
                eth_amount = _to_decimal(body.get("eth_amount", 0))
            except Exception:
                self.send_json_response({"error": "eth_amount must be a valid number"}, status=400)  # type: ignore[attr-defined]
                return
            ait_address = body.get("ait_address", "")

            if eth_amount <= 0 or not ait_address:
                self.send_json_response({"error": "eth_amount and ait_address required"}, status=400)  # type: ignore[attr-defined]
                return

            # Get bridge configuration
            bridge_eth_address = bridge_config.bridge_eth_address
            try:
                min_eth_deposit = _to_decimal(bridge_config.min_eth_deposit)
            except Exception:
                min_eth_deposit = Decimal("0.001")
            eth_network = bridge_config.eth_network

            if not bridge_eth_address:
                self.send_json_response({"error": "Bridge not configured - BRIDGE_ETH_ADDRESS not set"}, status=500)  # type: ignore[attr-defined]
                return

            # Validate minimum deposit
            if eth_amount < min_eth_deposit:
                self.send_json_response(  # type: ignore[attr-defined]
                    {"error": f"Minimum deposit is {min_eth_deposit} ETH", "min_deposit": str(min_eth_deposit)}, status=400
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

            # Calculate fee from configured rate
            fee_eth = eth_amount * Decimal(str(bridge_config.fee_rate))
            net_eth = eth_amount - fee_eth

            # Hex-encode the AIT address as UTF-8 for the tx data field
            # (matches what bridge_monitor.parse_ait_recipient decodes)
            transaction_data_hex = "0x" + ait_address.encode("utf-8").hex()

            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "status": "ready",
                    "message": "Send ETH to the bridge address with your AIT address in transaction data",
                    "instructions": {
                        "send_eth_to": bridge_eth_address,
                        "network": eth_network,
                        "amount_eth": str(eth_amount),
                        "transaction_data": ait_address,
                        "transaction_data_hex": transaction_data_hex,
                        "min_deposit": str(min_eth_deposit),
                    },
                    "estimate": {
                        "eth_amount": str(eth_amount),
                        "fee_eth": str(round(fee_eth, 8)),
                        "net_eth": str(round(net_eth, 8)),
                        "estimated_ait_amount": str(round(ait_amount, 6)) if ait_amount else None,
                        "eth_usd_price": str(eth_usd.price) if eth_usd else None,
                        "ait_usd_price": str(ait_usd.price) if ait_usd else None,
                        "ait_recipient": ait_address,
                    },
                },
                status=200,
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]

    def _verify_bridge_withdrawal_signatures(
        self, eth_address: str, ait_amount: Decimal, signatures: list[dict[str, str]]
    ) -> tuple[bool, int]:
        """Verify 2-of-n multi-sig signatures for an AIT→ETH bridge withdrawal."""
        signers = {s.strip().lower() for s in bridge_config.signers}
        threshold = bridge_config.multisig_threshold
        if not signers or threshold <= 0:
            return (True, 0)  # no multi-sig configured; gate is open

        try:
            from eth_keys import keys
        except Exception:
            # eth_keys not available; cannot verify signatures
            return (False, 0)

        message = f"BRIDGE_WITHDRAW:{eth_address}:{ait_amount}".encode()
        valid = set()
        for sig in signatures:
            try:
                sig_hex = sig.get("signature", "").removeprefix("0x")
                if not sig_hex:
                    continue
                signature = keys.Signature(bytes.fromhex(sig_hex))
                public_key = signature.recover_public_key_from_msg(message)
                addr = public_key.to_address().lower()
                if addr in signers:
                    valid.add(addr)
            except Exception:
                continue

        return (len(valid) >= threshold, len(valid))

    def handle_bridge_withdraw(self):
        """POST /v1/bridge/withdraw — initiate AIT→ETH bridge withdrawal (DISABLED).

        When BRIDGE_WITHDRAW_ENABLED is false this still validates any provided
        multi-sig signatures and returns the validation result, so integrators can
        test the 2-of-3 policy before withdrawals go live.
        """
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc")

            body = self._read_json_body()  # type: ignore[attr-defined]
            try:
                ait_amount = _to_decimal(body.get("ait_amount", 0))
            except Exception:
                self.send_json_response({"error": "ait_amount must be a valid number"}, status=400)  # type: ignore[attr-defined]
                return
            eth_address = body.get("eth_address", "")
            signatures = body.get("signatures", [])

            if ait_amount <= 0 or not eth_address:
                self.send_json_response({"error": "ait_amount and eth_address required"}, status=400)  # type: ignore[attr-defined]
                return

            # P1.3: require multi-sig threshold before any withdrawal can proceed
            ok, valid_count = self._verify_bridge_withdrawal_signatures(eth_address, ait_amount, signatures)
            if not ok:
                self.send_json_response(  # type: ignore[attr-defined]
                    {
                        "status": "forbidden",
                        "message": f"Bridge withdrawal requires {bridge_config.multisig_threshold} valid signer signatures; got {valid_count}.",
                        "required_signatures": bridge_config.multisig_threshold,
                        "valid_signatures": valid_count,
                    },
                    status=403,
                )
                return

            if not bridge_config.withdraw_enabled:
                self.send_json_response(  # type: ignore[attr-defined]
                    {
                        "status": "disabled",
                        "message": "AIT→ETH withdrawals are currently disabled. Only ETH→AIT deposits are supported.",
                        "reason": "Withdrawal functionality not yet enabled",
                        "supported_direction": "ETH → AIT (deposits only)",
                        "deposit_endpoint": "/v1/bridge/deposit",
                        "multisig_enabled": bridge_config.multisig_enabled,
                        "multisig_threshold": bridge_config.multisig_threshold,
                        "signatures_valid": valid_count,
                    },
                    status=503,
                )
                return

            # Withdrawals are enabled and multi-sig is satisfied. The release path
            # is intentionally a stub until the Ethereum bridge contract is deployed.
            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "status": "not_implemented",
                    "message": "Withdrawal multi-sig accepted; on-chain release is not yet deployed.",
                    "eth_address": eth_address,
                    "ait_amount": str(ait_amount),
                },
                status=501,
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]

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
                    self.send_json_response({"error": f"Invalid status: {status_filter}"}, status=400)  # type: ignore[attr-defined]
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
                    deposits_list.append(dict(d))  # type: ignore[unreachable]

            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "deposits": deposits_list,
                    "count": len(deposits_list),
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]

    def handle_bridge_deposit_detail(self, tx_hash):
        """GET /v1/bridge/deposit/{tx_hash} — get deposit details"""
        try:
            import sys

            sys.path.insert(0, "/opt/aitbc/apps/bridge-monitor/src")
            from bridge_monitor.storage import get_deposit

            deposit = get_deposit(tx_hash)
            if not deposit:
                self.send_json_response({"error": "Deposit not found"}, status=404)  # type: ignore[attr-defined]
                return

            self.send_json_response(deposit)  # type: ignore[attr-defined]
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]

    def handle_cross_chain_rates(self):
        """GET /cross-chain/rates or /v1/cross-chain/rates."""
        import sys

        sys.path.insert(0, "/opt/aitbc")
        try:
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            eth_usd = oracle.get_price("ETH", "USD")
            ait_usd = oracle.get_price("AIT", "USD")

            rates: dict[str, float] = {}
            if eth_usd and ait_usd and ait_usd.price > 0:
                rates["ETH::AITBC"] = float(round(eth_usd.price / ait_usd.price, 8))
            if eth_usd and ait_usd and eth_usd.price > 0:
                rates["AITBC::ETH"] = float(round(ait_usd.price / eth_usd.price, 8))

            self.send_json_response(
                {  # type: ignore[attr-defined]
                    "rates": rates,
                    "custodian": bridge_config.custodian,
                    "multisig_enabled": bridge_config.multisig_enabled,
                    "multisig_threshold": bridge_config.multisig_threshold,
                    "multisig_signers_count": len(bridge_config.signers),
                    "require_merkle_proof": False,
                    "note": "Bridge is operating in trusted-custodian mode; rates are indicative only.",
                }
            )
        except Exception:
            self.send_json_response(
                {  # type: ignore[attr-defined]
                    "rates": {},
                    "custodian": bridge_config.custodian,
                    "multisig_enabled": bridge_config.multisig_enabled,
                    "multisig_threshold": bridge_config.multisig_threshold,
                    "multisig_signers_count": len(bridge_config.signers),
                    "require_merkle_proof": False,
                    "note": "Bridge is operating in trusted-custodian mode; rate feed unavailable.",
                }
            )

    def handle_bridge_estimate(self):
        """POST /v1/bridge/estimate — estimate AIT amount for ETH"""
        if not self._require_api_key():  # type: ignore[attr-defined]
            return
        try:
            body = self._read_json_body()  # type: ignore[attr-defined]
            try:
                eth_amount = _to_decimal(body.get("eth_amount", 0))
            except Exception:
                self.send_json_response({"error": "eth_amount must be a valid number"}, status=400)  # type: ignore[attr-defined]
                return

            if eth_amount <= 0:
                self.send_json_response({"error": "eth_amount must be positive"}, status=400)  # type: ignore[attr-defined]
                return

            import sys

            sys.path.insert(0, "/opt/aitbc")
            from aitbc.oracles.price_oracle import get_price_oracle

            oracle = get_price_oracle()
            eth_usd_result = oracle.get_price("ETH", "USD")
            ait_usd_result = oracle.get_price("AIT", "USD")

            if not eth_usd_result or not ait_usd_result:
                self.send_json_response({"error": "Cannot get oracle prices"}, status=503)  # type: ignore[attr-defined]
                return

            eth_usd = eth_usd_result.price
            ait_usd = ait_usd_result.price

            if ait_usd <= 0:
                self.send_json_response({"error": "AIT/USD price is zero"}, status=503)  # type: ignore[attr-defined]
                return

            ait_amount = (eth_amount * eth_usd) / ait_usd

            self.send_json_response(  # type: ignore[attr-defined]
                {
                    "eth_amount": str(eth_amount),
                    "eth_usd_price": str(eth_usd),
                    "ait_usd_price": str(ait_usd),
                    "ait_amount": str(round(ait_amount, 6)),
                    "exchange_rate": str(round(ait_amount / eth_amount, 2)),
                }
            )
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)  # type: ignore[attr-defined]
