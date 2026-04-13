"""
Hub Discovery
DNS-based hub discovery for federated mesh with hardcoded fallback
"""

import asyncio
import logging
import socket
from typing import List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HubEndpoint:
    """Hub endpoint information"""
    address: str
    port: int
    source: str  # "dns" or "fallback"


class HubDiscovery:
    """DNS-based hub discovery with hardcoded fallback"""
    
    # Hardcoded fallback hubs for DNS failures
    FALLBACK_HUBS = [
        ("10.1.1.1", 7070),
        ("10.1.1.2", 7070),
        ("10.1.1.3", 7070),
    ]
    
    def __init__(self, discovery_url: str, default_port: int = 7070):
        self.discovery_url = discovery_url
        self.default_port = default_port
        self.cached_hubs: List[HubEndpoint] = []
        self.cache_time: float = 0
        self.cache_ttl = 300  # 5 minutes
    
    async def discover_hubs(self, use_fallback: bool = True) -> List[HubEndpoint]:
        """Discover hubs via DNS, with fallback if needed"""
        current_time = asyncio.get_event_loop().time()
        
        # Return cached results if still valid
        if self.cached_hubs and (current_time - self.cache_time) < self.cache_ttl:
            logger.debug(f"Returning cached hubs ({len(self.cached_hubs)} hubs)")
            return self.cached_hubs.copy()
        
        # Try DNS discovery
        dns_hubs = await self._discover_via_dns()
        
        if dns_hubs:
            self.cached_hubs = dns_hubs
            self.cache_time = current_time
            logger.info(f"Discovered {len(dns_hubs)} hubs via DNS")
            return dns_hubs
        elif use_fallback:
            # Use fallback hubs
            fallback_hubs = self._get_fallback_hubs()
            self.cached_hubs = fallback_hubs
            self.cache_time = current_time
            logger.warning(f"DNS discovery failed, using {len(fallback_hubs)} fallback hubs")
            return fallback_hubs
        else:
            logger.warning("DNS discovery failed and fallback disabled")
            return []
    
    async def _discover_via_dns(self) -> List[HubEndpoint]:
        """Discover hubs via DNS resolution"""
        try:
            # Resolve DNS to get IP addresses
            loop = asyncio.get_event_loop()
            
            # Get address info
            addr_info = await loop.getaddrinfo(self.discovery_url, self.default_port)
            
            hubs = []
            seen_addresses = set()
            
            for info in addr_info:
                address = info[4][0]  # IP address
                port = info[4][1] or self.default_port
                
                # Deduplicate addresses
                if address not in seen_addresses:
                    seen_addresses.add(address)
                    hubs.append(HubEndpoint(address=address, port=port, source="dns"))
            
            return hubs
            
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for {self.discovery_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"DNS discovery error: {e}")
            return []
    
    def _get_fallback_hubs(self) -> List[HubEndpoint]:
        """Get hardcoded fallback hubs"""
        return [
            HubEndpoint(address=address, port=port, source="fallback")
            for address, port in self.FALLBACK_HUBS
        ]
    
    async def register_hub(self, hub_address: str, hub_port: int, discovery_url: Optional[str] = None) -> bool:
        """
        Register this node as a hub (placeholder for future DNS registration)
        
        Note: This is a placeholder for future DNS registration functionality.
        Currently, hub registration is done via manual DNS configuration.
        """
        logger.info(f"Hub registration placeholder: {hub_address}:{hub_port}")
        # Future: Implement dynamic DNS registration
        return True
    
    def clear_cache(self):
        """Clear cached hub list"""
        self.cached_hubs = []
        self.cache_time = 0
        logger.debug("Cleared hub discovery cache")
    
    def get_cache_info(self) -> dict:
        """Get cache information"""
        current_time = asyncio.get_event_loop().time()
        cache_age = current_time - self.cache_time if self.cache_time else 0
        cache_valid = cache_age < self.cache_ttl
        
        return {
            "hub_count": len(self.cached_hubs),
            "cache_age": cache_age,
            "cache_valid": cache_valid,
            "cache_ttl": self.cache_ttl
        }


# Global hub discovery instance
hub_discovery_instance: Optional[HubDiscovery] = None


def get_hub_discovery() -> Optional[HubDiscovery]:
    """Get global hub discovery instance"""
    return hub_discovery_instance


def create_hub_discovery(discovery_url: str, default_port: int = 7070) -> HubDiscovery:
    """Create and set global hub discovery instance"""
    global hub_discovery_instance
    hub_discovery_instance = HubDiscovery(discovery_url, default_port)
    return hub_discovery_instance
