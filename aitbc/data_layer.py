"""
Data layer abstraction for AITBC
Provides toggle between mock and real data sources for development/testing
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC
import httpx


class DataLayer:
    """Data layer abstraction that can switch between mock and real data sources"""
    
    def __init__(self, use_mock_data: Optional[bool] = None):
        """Initialize data layer
        
        Args:
            use_mock_data: Force mock mode. If None, uses USE_MOCK_DATA env var
        """
        if use_mock_data is None:
            self.use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        else:
            self.use_mock_data = use_mock_data
        
        self.mock_generator = MockDataGenerator()
        self.real_fetcher = RealDataFetcher()
    
    async def get_transactions(
        self,
        address: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        tx_type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        chain_id: str = "ait-devnet",
        rpc_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get transactions from either mock or real data source"""
        if self.use_mock_data:
            return self.mock_generator.generate_transactions(
                address, amount_min, amount_max, tx_type, limit
            )
        else:
            return await self.real_fetcher.fetch_transactions(
                address, amount_min, amount_max, tx_type, since, until,
                limit, offset, chain_id, rpc_url
            )
    
    async def get_blocks(
        self,
        validator: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        min_tx: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        chain_id: str = "ait-devnet",
        rpc_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get blocks from either mock or real data source"""
        if self.use_mock_data:
            return self.mock_generator.generate_blocks(validator, min_tx, limit)
        else:
            return await self.real_fetcher.fetch_blocks(
                validator, since, until, min_tx, limit, offset, chain_id, rpc_url
            )
    
    async def get_analytics_overview(self, period: str = "24h", rpc_url: Optional[str] = None) -> Dict[str, Any]:
        """Get analytics overview from either mock or real data source"""
        if self.use_mock_data:
            return self.mock_generator.generate_analytics(period)
        else:
            return await self.real_fetcher.fetch_analytics(period, rpc_url)


class MockDataGenerator:
    """Generates mock data for development/testing when mock mode is enabled"""
    
    def generate_transactions(
        self,
        address: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        tx_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Generate mock transaction data"""
        from aitbc.testing import MockFactory, TestDataGenerator
        
        transactions = []
        for _ in range(limit):
            tx = TestDataGenerator.generate_transaction_data(
                from_address=address or MockFactory.generate_ethereum_address(),
                to_address=MockFactory.generate_ethereum_address()
            )
            if tx_type:
                tx["type"] = tx_type
            transactions.append(tx)
        
        return transactions
    
    def generate_blocks(
        self,
        validator: Optional[str] = None,
        min_tx: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Generate mock block data"""
        from aitbc.testing import MockFactory
        
        blocks = []
        for i in range(limit):
            blocks.append({
                "height": 10000 + i,
                "hash": MockFactory.generate_hash(),
                "validator": validator or MockFactory.generate_ethereum_address(),
                "tx_count": min_tx or 5,
                "timestamp": datetime.now(datetime.UTC).isoformat()
            })
        
        return blocks
    
    def generate_analytics(self, period: str = "24h") -> Dict[str, Any]:
        """Generate mock analytics data"""
        if period == "1h":
            labels = [f"{i:02d}:{(i*5)%60:02d}" for i in range(12)]
            volume_values = [10 + i * 2 for i in range(12)]
            activity_values = [5 + i for i in range(12)]
        elif period == "24h":
            labels = [f"{i:02d}:00" for i in range(0, 24, 2)]
            volume_values = [50 + i * 5 for i in range(12)]
            activity_values = [20 + i * 3 for i in range(12)]
        elif period == "7d":
            labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            volume_values = [500, 600, 550, 700, 800, 650, 750]
            activity_values = [200, 250, 220, 300, 350, 280, 320]
        else:  # 30d
            labels = [f"Week {i+1}" for i in range(4)]
            volume_values = [3000, 3500, 3200, 3800]
            activity_values = [1200, 1400, 1300, 1500]
        
        return {
            "total_transactions": "1,234",
            "transaction_volume": "5,678.90 AITBC",
            "active_addresses": "89",
            "avg_block_time": "2.1s",
            "volume_data": {
                "labels": labels,
                "values": volume_values
            },
            "activity_data": {
                "labels": labels,
                "values": activity_values
            }
        }


class RealDataFetcher:
    """Fetches real data from blockchain RPC endpoints"""
    
    async def fetch_transactions(
        self,
        address: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        tx_type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        chain_id: str = "ait-devnet",
        rpc_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch real transactions from blockchain RPC"""
        if rpc_url is None:
            rpc_url = f"http://localhost:8025"
        
        params = {}
        if address:
            params["address"] = address
        if amount_min:
            params["amount_min"] = amount_min
        if amount_max:
            params["amount_max"] = amount_max
        if tx_type:
            params["type"] = tx_type
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        params["limit"] = limit
        params["offset"] = offset
        params["chain_id"] = chain_id
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/search/transactions", params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return []
            else:
                raise Exception(f"Failed to fetch transactions: {response.status_code}")
    
    async def fetch_blocks(
        self,
        validator: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        min_tx: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        chain_id: str = "ait-devnet",
        rpc_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch real blocks from blockchain RPC"""
        if rpc_url is None:
            rpc_url = f"http://localhost:8025"
        
        params = {}
        if validator:
            params["validator"] = validator
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if min_tx:
            params["min_tx"] = min_tx
        params["limit"] = limit
        params["offset"] = offset
        params["chain_id"] = chain_id
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/search/blocks", params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return []
            else:
                raise Exception(f"Failed to fetch blocks: {response.status_code}")
    
    async def fetch_analytics(self, period: str = "24h", rpc_url: Optional[str] = None) -> Dict[str, Any]:
        """Fetch real analytics from blockchain RPC"""
        if rpc_url is None:
            rpc_url = f"http://localhost:8025"
        
        params = {"period": period}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/analytics/overview", params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise Exception("Analytics endpoint not available")
            else:
                raise Exception(f"Failed to fetch analytics: {response.status_code}")


# Global data layer instance
_data_layer: Optional[DataLayer] = None


def get_data_layer(use_mock_data: Optional[bool] = None) -> DataLayer:
    """Get or create global data layer instance"""
    global _data_layer
    if _data_layer is None:
        _data_layer = DataLayer(use_mock_data)
    return _data_layer
