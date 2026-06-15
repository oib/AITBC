"""
NAT Traversal Service
Handles STUN-based public endpoint discovery for P2P mesh networks
"""

import socket
from dataclasses import dataclass

from aitbc import get_logger

logger = get_logger(__name__)


@dataclass
class PublicEndpoint:
    """Public endpoint discovered via STUN"""

    address: str
    port: int
    stun_server: str
    nat_type: str = "unknown"


class STUNClient:
    """STUN client for discovering public IP:port endpoints"""

    def __init__(self, stun_servers: list[str]):
        """
        Initialize STUN client with list of STUN servers

        Args:
            stun_servers: List of STUN server addresses (format: "host:port")
        """
        self.stun_servers = stun_servers
        self.timeout = 5.0

    def _parse_server_address(self, server: str) -> tuple[str, int]:
        """Parse STUN server address string"""
        parts = server.split(":")
        if len(parts) == 2:
            return (parts[0], int(parts[1]))
        elif len(parts) == 1:
            return (parts[0], 3478)
        else:
            raise ValueError(f"Invalid STUN server format: {server}")

    async def discover_public_endpoint(self) -> PublicEndpoint | None:
        """
        Discover public IP:port using STUN servers

        Returns:
            PublicEndpoint if successful, None otherwise
        """
        for stun_server in self.stun_servers:
            try:
                host, port = self._parse_server_address(stun_server)
                logger.info("Querying STUN server: %s:%s", host, port)
                endpoint = await self._stun_request(host, port)
                if endpoint:
                    logger.info("Discovered public endpoint: %s:%s via %s", endpoint.address, endpoint.port, stun_server)
                    return endpoint
            except Exception as e:
                logger.warning("STUN query failed for %s: %s", stun_server, e)
                continue
        logger.error("Failed to discover public endpoint from all STUN servers")
        return None

    async def _stun_request(self, host: str, port: int) -> PublicEndpoint | None:
        """
        Perform STUN request to discover public endpoint using UDP

        Args:
            host: STUN server hostname
            port: STUN server port

        Returns:
            PublicEndpoint if successful, None otherwise
        """
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            stun_request = bytearray([0, 1, 0, 0, 33, 18, 164, 66, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
            sock.sendto(stun_request, (host, port))
            response, addr = sock.recvfrom(1024)
            sock.close()
            return self._parse_stun_response(response, f"{host}:{port}")
        except TimeoutError:
            logger.warning("STUN request to %s:%s timed out", host, port)
            return None
        except Exception as e:
            logger.error("STUN request to %s:%s failed: %s", host, port, e)
            return None

    def _parse_stun_response(self, response: bytes, stun_server: str) -> PublicEndpoint | None:
        """
        Parse STUN response to extract public endpoint

        Args:
            response: STUN response bytes
            stun_server: STUN server address for logging

        Returns:
            PublicEndpoint if successful, None otherwise
        """
        try:
            if len(response) < 20:
                logger.warning("Invalid STUN response length: %s", len(response))
                return None
            magic_cookie = response[4:8]
            if magic_cookie != b"!\x12\xa4B":
                logger.warning("Invalid STUN magic cookie in response")
                return None
            msg_type = response[0] << 8 | response[1]
            if msg_type != 257:
                logger.warning("Unexpected STUN message type: 0x%s", msg_type)
                return None
            pos = 20
            while pos < len(response):
                if pos + 4 > len(response):
                    break
                attr_type = response[pos] << 8 | response[pos + 1]
                attr_length = response[pos + 2] << 8 | response[pos + 3]
                pos += 4
                if pos + attr_length > len(response):
                    break
                if attr_type == 32:
                    family = response[pos + 1]
                    if family == 1:
                        port = response[pos + 2] << 8 | response[pos + 3]
                        ip_bytes = response[pos + 4 : pos + 8]
                        ip = socket.inet_ntoa(bytes([ip_bytes[0] ^ 33, ip_bytes[1] ^ 18, ip_bytes[2] ^ 164, ip_bytes[3] ^ 66]))
                        port = port ^ 8466
                        return PublicEndpoint(ip, port, stun_server, "full_cone")
                pos += attr_length
            logger.warning("No XOR-MAPPED-ADDRESS found in STUN response")
            return None
        except Exception as e:
            logger.error("Failed to parse STUN response: %s", e)
            return None


class NATTraversalService:
    """NAT traversal service for P2P networks"""

    def __init__(self, stun_servers: list[str]):
        """
        Initialize NAT traversal service

        Args:
            stun_servers: List of STUN server addresses
        """
        self.stun_servers = stun_servers
        self.stun_client = STUNClient(stun_servers)
        self.public_endpoint: PublicEndpoint | None = None

    async def discover_endpoint(self) -> PublicEndpoint | None:
        """
        Discover public endpoint using STUN

        Returns:
            PublicEndpoint if successful, None otherwise
        """
        if not self.stun_servers:
            logger.warning("No STUN servers configured")
            return None
        self.public_endpoint = await self.stun_client.discover_public_endpoint()
        return self.public_endpoint

    def get_public_endpoint(self) -> tuple[str, int] | None:
        """
        Get discovered public endpoint

        Returns:
            Tuple of (address, port) if discovered, None otherwise
        """
        if self.public_endpoint:
            return (self.public_endpoint.address, self.public_endpoint.port)
        return None

    def get_nat_type(self) -> str:
        """
        Get discovered NAT type

        Returns:
            NAT type string
        """
        if self.public_endpoint:
            return self.public_endpoint.nat_type
        return "unknown"


nat_traversal_service: NATTraversalService | None = None


def get_nat_traversal() -> NATTraversalService | None:
    """Get global NAT traversal instance"""
    return nat_traversal_service


def create_nat_traversal(stun_servers: list[str]) -> NATTraversalService:
    """
    Create and set global NAT traversal instance

    Args:
        stun_servers: List of STUN server addresses

    Returns:
        NATTraversalService instance
    """
    global nat_traversal_service
    nat_traversal_service = NATTraversalService(stun_servers)
    return nat_traversal_service
