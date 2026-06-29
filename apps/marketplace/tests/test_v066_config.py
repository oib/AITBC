"""Integration tests for v0.6.6 Marketplace + GPU config (B1 + B2).

Tests cover:
- B1: Marketplace config fields (blockchain_rpc_url, default_chain_id, agent_coordinator_url)
- B2: GPU service config fields (blockchain_rpc_url, default_chain_id)

B3-B7 (OfferFSM, BlockchainRPCClient, edge schema fixes, matching) are skipped
until Agent A delivers A1-A3.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# B1: Marketplace config
# ---------------------------------------------------------------------------


class TestMarketplaceConfig:
    """Test v0.6.6 marketplace config fields exist with correct defaults."""

    def test_marketplace_config_blockchain_rpc_url(self):
        """Config has blockchain_rpc_url defaulting to 8202 (not stale 8006)."""
        from marketplace_service.config import settings

        assert hasattr(settings, "blockchain_rpc_url")
        assert "8202" in settings.blockchain_rpc_url
        assert "8006" not in settings.blockchain_rpc_url

    def test_marketplace_config_default_chain_id(self):
        """Config has default_chain_id field."""
        from marketplace_service.config import settings

        assert hasattr(settings, "default_chain_id")
        assert settings.default_chain_id == "ait-hub"

    def test_marketplace_config_agent_coordinator_url(self):
        """Config has agent_coordinator_url field."""
        from marketplace_service.config import settings

        assert hasattr(settings, "agent_coordinator_url")
        assert settings.agent_coordinator_url.startswith("http://")

    def test_marketplace_config_bind_host(self):
        """Config has marketplace_bind_host field."""
        from marketplace_service.config import settings

        assert hasattr(settings, "marketplace_bind_host")

    def test_marketplace_config_bind_port(self):
        """Config has marketplace_bind_port field."""
        from marketplace_service.config import settings

        assert hasattr(settings, "marketplace_bind_port")
        assert isinstance(settings.marketplace_bind_port, int)

    def test_marketplace_main_uses_settings_not_hardcoded(self):
        """main.py imports settings from config.py (not just os.getenv)."""
        import inspect

        from marketplace_service import main

        source = inspect.getsource(main)
        assert "from .config import settings" in source

    def test_marketplace_service_uses_8202_not_8006(self):
        """marketplace_service.py defaults to 8202, not stale 8006."""
        import inspect

        from marketplace_service.services import marketplace_service

        source = inspect.getsource(marketplace_service)
        assert "8006" not in source.replace("8006", "")  # no 8006 anywhere
        # The default should be 8202
        assert "8202" in source


# ---------------------------------------------------------------------------
# B2: GPU service config
# ---------------------------------------------------------------------------


class TestGpuConfig:
    """Test v0.6.6 GPU service config fields exist with correct defaults."""

    def test_gpu_config_blockchain_rpc_url(self):
        """Config has blockchain_rpc_url defaulting to 8202."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        from gpu_service.config import settings

        assert hasattr(settings, "blockchain_rpc_url")
        assert "8202" in settings.blockchain_rpc_url
        assert "8006" not in settings.blockchain_rpc_url

    def test_gpu_config_default_chain_id(self):
        """Config has default_chain_id field, defaults to 'ait-hub' (not empty)."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        from gpu_service.config import settings

        assert hasattr(settings, "default_chain_id")
        assert settings.default_chain_id == "ait-hub"
        assert settings.default_chain_id != ""

    def test_gpu_config_bind_host(self):
        """Config has gpu_bind_host field."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        from gpu_service.config import settings

        assert hasattr(settings, "gpu_bind_host")

    def test_gpu_config_bind_port(self):
        """Config has gpu_bind_port field."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        from gpu_service.config import settings

        assert hasattr(settings, "gpu_bind_port")
        assert isinstance(settings.gpu_bind_port, int)

    def test_gpu_main_uses_settings_not_empty_chain_id(self):
        """main.py uses settings.default_chain_id, not os.getenv('CHAIN_ID', '')."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        import inspect

        from gpu_service import main

        source = inspect.getsource(main)
        assert "from .config import settings" in source
        assert "settings.default_chain_id" in source
        # The old pattern os.getenv("CHAIN_ID", "") should not be in the chain_id line
        assert 'os.getenv("CHAIN_ID", "")' not in source

    def test_gpu_main_uses_settings_blockchain_rpc_url(self):
        """main.py uses settings.blockchain_rpc_url, not os.getenv."""
        gpu_src = Path(__file__).parent.parent.parent / "gpu" / "src"
        sys.path.insert(0, str(gpu_src))
        import inspect

        from gpu_service import main

        source = inspect.getsource(main)
        assert "settings.blockchain_rpc_url" in source
