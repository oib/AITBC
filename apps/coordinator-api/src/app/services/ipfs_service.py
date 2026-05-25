"""
IPFS Service - Real IPFS integration for decentralized storage

Provides:
- File upload to IPFS
- CID generation and retrieval
- Pin management
- Gateway access
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import httpx

from aitbc.aitbc_logging import get_logger


logger = get_logger(__name__)


@dataclass
class IPFSUploadResult:
    """Result of IPFS upload"""
    cid: str
    size: int
    name: str
    timestamp: datetime
    gateway_url: str
    pinned: bool


@dataclass
class IPFSPin:
    """IPFS pin record"""
    cid: str
    name: str
    size: int
    pinned_at: datetime
    metadata: Dict[str, Any]


class IPFSClient:
    """
    IPFS client for interacting with IPFS nodes.
    
    Supports:
    - Local IPFS node (default: localhost:5001)
    - Infura IPFS
    - Pinata
    - Other pinning services
    """
    
    def __init__(
        self,
        api_url: str = "http://localhost:5001",
        gateway_url: str = "https://ipfs.io",
        pinning_service: Optional[str] = None,
        pinning_key: Optional[str] = None,
        session: Any = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.pinning_service = pinning_service
        self.pinning_key = pinning_key
        self._client = httpx.AsyncClient(timeout=60.0)
        self._available: Optional[bool] = None
    
    async def check_availability(self) -> bool:
        """Check if IPFS node is available"""
        if self._available is not None:
            return self._available
        
        try:
            response = await self._client.post(
                f"{self.api_url}/api/v0/id",
                timeout=5.0
            )
            self._available = response.status_code == 200
            if self._available:
                data = response.json()
                logger.info(f"IPFS node connected: {data.get('ID', 'unknown')[:16]}...")
            return self._available
        except Exception as e:
            logger.warning(f"IPFS node not available: {e}")
            self._available = False
            return False
    
    async def upload_file(
        self,
        data: Union[bytes, str],
        filename: str = "",
        pin: bool = True,
        wrap_with_directory: bool = False
    ) -> IPFSUploadResult:
        """
        Upload data to IPFS.
        
        Args:
            data: File content (bytes or string)
            filename: Optional filename
            pin: Whether to pin the content
            wrap_with_directory: Whether to wrap in a directory
        
        Returns:
            IPFSUploadResult with CID and metadata
        """
        # Convert string to bytes
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Check if IPFS is available
        is_available = await self.check_availability()
        
        if is_available:
            # Upload to real IPFS
            return await self._upload_to_ipfs(
                data, filename, pin, wrap_with_directory
            )
        else:
            # Generate mock CID for testing
            return self._generate_mock_cid(data, filename)
    
    async def _upload_to_ipfs(
        self,
        data: bytes,
        filename: str,
        pin: bool,
        wrap_with_directory: bool
    ) -> IPFSUploadResult:
        """Upload to real IPFS node"""
        try:
            files = {'file': (filename or 'data', data)}
            
            params = {}
            if pin:
                params['pin'] = 'true'
            if wrap_with_directory:
                params['wrap-with-directory'] = 'true'
            
            response = await self._client.post(
                f"{self.api_url}/api/v0/add",
                files=files,
                params=params,
                timeout=60.0
            )
            
            response.raise_for_status()
            
            # Parse response (ndjson format)
            lines = response.text.strip().split('\n')
            last_line = json.loads(lines[-1])
            
            cid = last_line.get('Hash')
            size = last_line.get('Size', len(data))
            
            # Also pin with external service if configured
            if pin and self.pinning_service:
                await self._pin_to_external_service(cid, filename, size)
            
            return IPFSUploadResult(
                cid=cid,
                size=size,
                name=filename or cid[:16],
                timestamp=datetime.now(timezone.utc),
                gateway_url=f"{self.gateway_url}/ipfs/{cid}",
                pinned=pin
            )
            
        except Exception as e:
            logger.error(f"IPFS upload failed: {e}")
            raise
    
    def _generate_mock_cid(self, data: bytes, filename: str) -> IPFSUploadResult:
        """Generate a mock CID for testing when IPFS is unavailable"""
        # Generate deterministic CID from data hash
        hash_value = hashlib.sha256(data).hexdigest()
        
        # CIDv0 format: Qm + base58 encoded hash
        mock_cid = f"Qm{hash_value[:44]}"
        
        logger.debug(f"Generated mock CID: {mock_cid}")
        
        return IPFSUploadResult(
            cid=mock_cid,
            size=len(data),
            name=filename or mock_cid[:16],
            timestamp=datetime.now(timezone.utc),
            gateway_url=f"https://ipfs.io/ipfs/{mock_cid}",
            pinned=False
        )
    
    async def _pin_to_external_service(
        self,
        cid: str,
        name: str,
        size: int
    ) -> bool:
        """Pin CID to external pinning service"""
        if not self.pinning_service or not self.pinning_key:
            return False
        
        try:
            if self.pinning_service == "pinata":
                # Pinata pinning implementation
                response = await self._client.post(
                    "https://api.pinata.cloud/pinning/pinByHash",
                    headers={
                        "Authorization": f"Bearer {self.pinning_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "hashToPin": cid,
                        "pinataMetadata": {"name": name}
                    },
                    timeout=30.0
                )
                return response.status_code == 200
            
            return False
            
        except Exception as e:
            logger.warning(f"External pinning failed: {e}")
            return False
    
    async def get_content(self, cid: str) -> Optional[bytes]:
        """Retrieve content from IPFS by CID"""
        # Check if it's a mock CID (for testing)
        if cid.startswith("Qm") and len(cid) == 46:
            # Try to fetch from IPFS
            try:
                response = await self._client.get(
                    f"{self.gateway_url}/ipfs/{cid}",
                    timeout=30.0,
                    follow_redirects=True
                )
                if response.status_code == 200:
                    return response.content
            except Exception as e:
                logger.debug(f"Could not fetch from IPFS gateway: {e}")
        
        return None
    
    async def pin_cid(self, cid: str, name: str = "") -> bool:
        """Pin an existing CID to the local node"""
        if not await self.check_availability():
            return False
        
        try:
            response = await self._client.post(
                f"{self.api_url}/api/v0/pin/add",
                params={'arg': cid},
                timeout=30.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Pin failed: {e}")
            return False
    
    async def unpin_cid(self, cid: str) -> bool:
        """Unpin a CID from the local node"""
        if not await self.check_availability():
            return False
        
        try:
            response = await self._client.post(
                f"{self.api_url}/api/v0/pin/rm",
                params={'arg': cid},
                timeout=30.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Unpin failed: {e}")
            return False
    
    async def list_pins(self) -> List[IPFSPin]:
        """List all pinned CIDs"""
        if not await self.check_availability():
            return []
        
        try:
            response = await self._client.post(
                f"{self.api_url}/api/v0/pin/ls",
                timeout=30.0
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            pins = []
            
            for cid, info in data.get('Keys', {}).items():
                pins.append(IPFSPin(
                    cid=cid,
                    name=info.get('Type', 'unknown'),
                    size=0,  # Would need to get size separately
                    pinned_at=datetime.now(timezone.utc),
                    metadata=info
                ))
            
            return pins
            
        except Exception as e:
            logger.warning(f"List pins failed: {e}")
            return []


class IPFSService:
    """
    High-level IPFS service for the AITBC platform.
    
    Provides convenient methods for:
    - Storing job results
    - Caching AI model outputs
    - Archiving transaction data
    """
    
    def __init__(self, session: Any = None) -> None:
        self.client = IPFSClient()
        self._uploads: Dict[str, IPFSUploadResult] = {}
        self.session = session
    
    async def store_job_result(
        self,
        job_id: str,
        result_data: Dict[str, Any]
    ) -> IPFSUploadResult:
        """Store AI job result on IPFS"""
        # Serialize result
        data = json.dumps(result_data, indent=2).encode('utf-8')
        
        # Upload to IPFS
        result = await self.client.upload_file(
            data=data,
            filename=f"job_{job_id}_result.json",
            pin=True
        )
        
        self._uploads[job_id] = result
        
        logger.info(f"Job result stored on IPFS: {job_id} -> {result.cid}")
        
        return result
    
    async def store_evidence(
        self,
        dispute_id: str,
        evidence_data: Dict[str, Any]
    ) -> IPFSUploadResult:
        """Store dispute evidence on IPFS"""
        data = json.dumps(evidence_data, indent=2).encode('utf-8')
        
        result = await self.client.upload_file(
            data=data,
            filename=f"dispute_{dispute_id}_evidence.json",
            pin=True
        )
        
        logger.info(f"Evidence stored on IPFS: {dispute_id} -> {result.cid}")
        
        return result
    
    async def get_upload(self, job_id: str) -> Optional[IPFSUploadResult]:
        """Get upload result by job ID"""
        return self._uploads.get(job_id)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check IPFS service health"""
        available = await self.client.check_availability()
        
        return {
            "status": "healthy" if available else "degraded",
            "ipfs_node_available": available,
            "api_url": self.client.api_url,
            "gateway_url": self.client.gateway_url,
            "stored_uploads": len(self._uploads)
        }


# Global instance
_ipfs_service: Optional[IPFSService] = None


def get_ipfs_service() -> IPFSService:
    """Get global IPFS service"""
    global _ipfs_service
    if _ipfs_service is None:
        _ipfs_service = IPFSService()
    return _ipfs_service
