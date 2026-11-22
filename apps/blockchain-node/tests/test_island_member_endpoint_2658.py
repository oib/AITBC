"""#2658: the hub's own entry in the island member list must carry the
node's advertised host and configured P2P port, not the 127.0.0.1:7070
literals — a remote joiner dialing that entry reaches itself."""

from __future__ import annotations

from types import SimpleNamespace

from aitbc_chain.rpc import islands as rpc_islands


def _hub_manager() -> SimpleNamespace:
    island = SimpleNamespace(is_hub=True, island_id="island-1", island_name="island1", chain_id="ait-island1")
    return SimpleNamespace(
        local_node_id="hub-node",
        island_peers={"island-1": {"peer-a"}},
        get_island_info=lambda _iid: island,
    )


def test_hub_member_uses_advertised_host_and_configured_p2p_port(monkeypatch):
    monkeypatch.setenv("AITBC_HOSTNAME", "hub.example.net")
    monkeypatch.setenv("P2P_BIND_PORT", "8200")

    members = rpc_islands._island_members(_hub_manager(), "island-1")

    hub = members[0]
    assert hub == {"node_id": "hub-node", "is_hub": True, "address": "hub.example.net", "port": 8200}
    assert members[1] == {"node_id": "peer-a", "is_hub": False}


def test_hub_member_port_follows_p2p_bind_port_default(monkeypatch):
    """With P2P_BIND_PORT unset the port is the documented 7070 relay default,
    not the dormant-mesh settings default of 8200."""
    monkeypatch.delenv("P2P_BIND_PORT", raising=False)
    monkeypatch.setenv("AITBC_HOSTNAME", "hub.example.net")

    members = rpc_islands._island_members(_hub_manager(), "island-1")

    assert members[0]["port"] == 7070
    assert members[0]["address"] == "hub.example.net"
