"""AUDIT-EDGE-CLI-SYNC-SOURCE-USERINFO (#2800): ``network set-sync-source``
persisted ``user:pass@`` userinfo from --url into node env files and echoed
it in the updated list. Userinfo is now stripped before deriving values.
"""

import json


def test_derive_sync_urls_strips_userinfo():
    from aitbc_cli.commands.network import _derive_sync_urls

    values = _derive_sync_urls("https://user:s3cret@hub.example.net:8443/rpc")
    blob = json.dumps(values)
    assert "s3cret" not in blob
    assert values["BLOCKCHAIN_RPC_URL"] == "https://hub.example.net:8443"
    assert values["HUB_BLOCKCHAIN_RPC_URL"] == "https://hub.example.net:8443/rpc"
    assert values["HUB_DISCOVERY_URL"] == "hub.example.net"


def test_derive_sync_urls_plain_url_unchanged():
    from aitbc_cli.commands.network import _derive_sync_urls

    values = _derive_sync_urls("https://hub.example.net")
    assert values["BLOCKCHAIN_RPC_URL"] == "https://hub.example.net"
    assert values["HUB_DISCOVERY_URL"] == "hub.example.net"
