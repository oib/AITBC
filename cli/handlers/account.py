"""Account handlers."""

import json
import logging
import sys

from aitbc import AITBCHTTPClient, NetworkError

logger = logging.getLogger(__name__)


def render_mapping(title, mapping):
    """Render a mapping dictionary to console."""
    print(f"{title}")
    for key, value in mapping.items():
        print(f"  {key}: {value}")


def handle_account_get(args, default_rpc_url, output_format):
    """Handle account get command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.address:
        logger.error("Error: --address is required")
        sys.exit(1)

    logger.info("Getting account %s from %s...", args.address, rpc_url)
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        account = http_client.get(f"/rpc/account/{args.address}", params=params)
        if output_format(args) == "json":
            logger.info(json.dumps(account, indent=2))
        else:
            render_mapping(f"Account {args.address}:", account)
    except NetworkError as e:
        logger.error("Error getting account: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Error getting account: %s", e)
        sys.exit(1)
