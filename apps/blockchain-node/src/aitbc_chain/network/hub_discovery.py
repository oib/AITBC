"""
Hub Discovery
DNS-based hub discovery for federated mesh with hardcoded fallback
"""

import asyncio
import socket
from dataclasses import dataclass
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class HubEndpoint:
    """Hub endpoint information"""

    address: str
    port: int
    source: str


class HubDiscovery:
    """DNS-based hub discovery with hardcoded fallback"""

    FALLBACK_HUBS = [("10.1.1.1", 7070), ("10.1.1.2", 7070), ("10.1.1.3", 7070)]

    def __init__(self, discovery_url: str, default_port: int = 7070):
        self.discovery_url = discovery_url
        self.default_port = default_port
        self.cached_hubs: list[HubEndpoint] = []
        self.cache_time: float = 0
        self.cache_ttl = 300

    async def discover_hubs(self, use_fallback: bool = True) -> list[HubEndpoint]:
        """Discover hubs via DNS, with fallback if needed"""
        current_time = asyncio.get_event_loop().time()
        if self.cached_hubs and current_time - self.cache_time < self.cache_ttl:
            logger.debug("Returning cached hubs (%s hubs)", len(self.cached_hubs))
            return self.cached_hubs.copy()
        dns_hubs = await self._discover_via_dns()
        if dns_hubs:
            self.cached_hubs = dns_hubs
            self.cache_time = current_time
            logger.info("Discovered %s hubs via DNS", len(dns_hubs))
            return dns_hubs
        elif use_fallback:
            fallback_hubs = self._get_fallback_hubs()
            self.cached_hubs = fallback_hubs
            self.cache_time = current_time
            logger.warning("DNS discovery failed, using %s fallback hubs", len(fallback_hubs))
            return fallback_hubs
        else:
            logger.warning("DNS discovery failed and fallback disabled")
            return []

    async def _discover_via_dns(self) -> list[HubEndpoint]:
        """Discover hubs via DNS resolution"""
        try:
            loop = asyncio.get_event_loop()
            addr_info = await loop.getaddrinfo(self.discovery_url, self.default_port)
            hubs = []
            seen_addresses = set()
            for info in addr_info:
                address = info[4][0]
                port = info[4][1] or self.default_port
                if address not in seen_addresses:
                    seen_addresses.add(address)
                    hubs.append(HubEndpoint(address=address, port=port, source="dns"))
            return hubs
        except socket.gaierror as e:
            logger.error("DNS resolution failed for %s: %s", self.discovery_url, e)
            return []
        except Exception as e:
            logger.error("DNS discovery error: %s", e)
            return []

    def _get_fallback_hubs(self) -> list[HubEndpoint]:
        """Get hardcoded fallback hubs"""
        return [HubEndpoint(address=address, port=port, source="fallback") for address, port in self.FALLBACK_HUBS]

    async def register_hub(self, hub_info: dict[str, Any], discovery_url: str | None = None) -> bool:
        """
        Register this node as a hub with DNS discovery service

        Args:
            hub_info: Dictionary containing hub information (node_id, address, port, island_id, island_name, public_address, public_port, public_key_pem)
            discovery_url: Optional custom discovery URL (uses default if not provided)

        Returns:
            bool: True if registration successful, False otherwise
        """
        url = discovery_url or self.discovery_url
        registration_url = f"https://{url}/api/register"
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(registration_url, json=hub_info)
                if response.status_code == 200:
                    logger.info("Successfully registered hub %s with DNS discovery service", hub_info.get("node_id"))
                    return True
                else:
                    logger.error("DNS registration failed: %s - %s", response.status_code, response.text)
                    return False
        except httpx.RequestError as e:
            logger.error("DNS registration request failed: %s", e)
            return False
        except Exception as e:
            logger.error("DNS registration error: %s", e)
            return False

    async def unregister_hub(self, node_id: str, discovery_url: str | None = None) -> bool:
        """
        Unregister this node as a hub from DNS discovery service

        Args:
            node_id: Node ID to unregister
            discovery_url: Optional custom discovery URL (uses default if not provided)

        Returns:
            bool: True if unregistration successful, False otherwise
        """
        url = discovery_url or self.discovery_url
        unregistration_url = f"https://{url}/api/unregister"
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(unregistration_url, json={"node_id": node_id})
                if response.status_code == 200:
                    logger.info("Successfully unregistered hub %s from DNS discovery service", node_id)
                    return True
                else:
                    logger.error("DNS unregistration failed: %s - %s", response.status_code, response.text)
                    return False
        except httpx.RequestError as e:
            logger.error("DNS unregistration request failed: %s", e)
            return False
        except Exception as e:
            logger.error("DNS unregistration error: %s", e)
            return False

    def clear_cache(self) -> None:
        """Clear cached hub list"""
        self.cached_hubs = []
        self.cache_time = 0
        logger.debug("Cleared hub discovery cache")

    def get_cache_info(self) -> dict[str, Any]:
        """Get cache information"""
        current_time = asyncio.get_event_loop().time()
        cache_age = current_time - self.cache_time if self.cache_time else 0
        cache_valid = cache_age < self.cache_ttl
        return {
            "hub_count": len(self.cached_hubs),
            "cache_age": cache_age,
            "cache_valid": cache_valid,
            "cache_ttl": self.cache_ttl,
        }


hub_discovery_instance: HubDiscovery | None = None


def get_hub_discovery() -> HubDiscovery | None:
    """Get global hub discovery instance"""
    return hub_discovery_instance


def create_hub_discovery(discovery_url: str, default_port: int = 7070) -> HubDiscovery:
    """Create and set global hub discovery instance"""
    global hub_discovery_instance
    hub_discovery_instance = HubDiscovery(discovery_url, default_port)
    return hub_discovery_instance
