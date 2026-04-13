"""
NAT Traversal Service
Handles STUN-based public endpoint discovery for P2P mesh networks
"""

import asyncio
import logging
import socket
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PublicEndpoint:
    """Public endpoint discovered via STUN"""
    address: str
    port: int
    stun_server: str
    nat_type: str = "unknown"


class STUNClient:
    """STUN client for discovering public IP:port endpoints"""
    
    def __init__(self, stun_servers: List[str]):
        """
        Initialize STUN client with list of STUN servers
        
        Args:
            stun_servers: List of STUN server addresses (format: "host:port")
        """
        self.stun_servers = stun_servers
        self.timeout = 5.0  # seconds
        
    def _parse_server_address(self, server: str) -> Tuple[str, int]:
        """Parse STUN server address string"""
        parts = server.split(':')
        if len(parts) == 2:
            return parts[0], int(parts[1])
        elif len(parts) == 1:
            return parts[0], 3478  # Default STUN port
        else:
            raise ValueError(f"Invalid STUN server format: {server}")
    
    async def discover_public_endpoint(self) -> Optional[PublicEndpoint]:
        """
        Discover public IP:port using STUN servers
        
        Returns:
            PublicEndpoint if successful, None otherwise
        """
        for stun_server in self.stun_servers:
            try:
                host, port = self._parse_server_address(stun_server)
                logger.info(f"Querying STUN server: {host}:{port}")
                
                # Create STUN request
                endpoint = await self._stun_request(host, port)
                
                if endpoint:
                    logger.info(f"Discovered public endpoint: {endpoint.address}:{endpoint.port} via {stun_server}")
                    return endpoint
                    
            except Exception as e:
                logger.warning(f"STUN query failed for {stun_server}: {e}")
                continue
        
        logger.error("Failed to discover public endpoint from all STUN servers")
        return None
    
    async def _stun_request(self, host: str, port: int) -> Optional[PublicEndpoint]:
        """
        Perform STUN request to discover public endpoint using UDP
        
        Args:
            host: STUN server hostname
            port: STUN server port
            
        Returns:
            PublicEndpoint if successful, None otherwise
        """
        try:
            # STUN uses UDP, not TCP
            import socket
            
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # Simple STUN binding request
            stun_request = bytearray([
                0x00, 0x01,  # Binding Request
                0x00, 0x00,  # Length
                0x21, 0x12, 0xa4, 0x42,  # Magic Cookie
                0x00, 0x00, 0x00, 0x00,  # Transaction ID (part 1)
                0x00, 0x00, 0x00, 0x00,  # Transaction ID (part 2)
                0x00, 0x00, 0x00, 0x00,  # Transaction ID (part 3)
            ])
            
            # Send STUN request
            sock.sendto(stun_request, (host, port))
            
            # Receive response
            response, addr = sock.recvfrom(1024)
            sock.close()
            
            # Parse STUN response
            return self._parse_stun_response(response, f"{host}:{port}")
            
        except socket.timeout:
            logger.warning(f"STUN request to {host}:{port} timed out")
            return None
        except Exception as e:
            logger.error(f"STUN request to {host}:{port} failed: {e}")
            return None
    
    def _parse_stun_response(self, response: bytes, stun_server: str) -> Optional[PublicEndpoint]:
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
                logger.warning(f"Invalid STUN response length: {len(response)}")
                return None
            
            # Check STUN magic cookie
            magic_cookie = response[4:8]
            if magic_cookie != b'\x21\x12\xa4\x42':
                logger.warning("Invalid STUN magic cookie in response")
                return None
            
            # Check message type (Binding Response = 0x0101)
            msg_type = (response[0] << 8) | response[1]
            if msg_type != 0x0101:
                logger.warning(f"Unexpected STUN message type: 0x{msg_type:04x}")
                return None
            
            # Parse attributes
            pos = 20
            while pos < len(response):
                if pos + 4 > len(response):
                    break
                
                attr_type = (response[pos] << 8) | response[pos + 1]
                attr_length = (response[pos + 2] << 8) | response[pos + 3]
                pos += 4
                
                if pos + attr_length > len(response):
                    break
                
                # XOR-MAPPED-ADDRESS attribute (0x0020)
                if attr_type == 0x0020:
                    family = response[pos + 1]
                    if family == 0x01:  # IPv4
                        port = (response[pos + 2] << 8) | response[pos + 3]
                        ip_bytes = response[pos + 4:pos + 8]
                        # XOR with magic cookie
                        ip = socket.inet_ntoa(bytes([
                            ip_bytes[0] ^ 0x21,
                            ip_bytes[1] ^ 0x12,
                            ip_bytes[2] ^ 0xa4,
                            ip_bytes[3] ^ 0x42
                        ]))
                        port = port ^ 0x2112
                        return PublicEndpoint(ip, port, stun_server, "full_cone")
                
                pos += attr_length
            
            logger.warning("No XOR-MAPPED-ADDRESS found in STUN response")
            return None
            
        except Exception as e:
            logger.error(f"Failed to parse STUN response: {e}")
            return None


class NATTraversalService:
    """NAT traversal service for P2P networks"""
    
    def __init__(self, stun_servers: List[str]):
        """
        Initialize NAT traversal service
        
        Args:
            stun_servers: List of STUN server addresses
        """
        self.stun_servers = stun_servers
        self.stun_client = STUNClient(stun_servers)
        self.public_endpoint: Optional[PublicEndpoint] = None
        
    async def discover_endpoint(self) -> Optional[PublicEndpoint]:
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
    
    def get_public_endpoint(self) -> Optional[Tuple[str, int]]:
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


# Global NAT traversal instance
nat_traversal_service: Optional[NATTraversalService] = None


def get_nat_traversal() -> Optional[NATTraversalService]:
    """Get global NAT traversal instance"""
    return nat_traversal_service


def create_nat_traversal(stun_servers: List[str]) -> NATTraversalService:
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
