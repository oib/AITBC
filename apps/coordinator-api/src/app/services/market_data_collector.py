"""
Market Data Collector for Dynamic Pricing Engine
Collects real-time market data from various sources for pricing calculations
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import websockets
from aitbc.logging import get_logger

logger = get_logger(__name__)


class DataSource(str, Enum):
    """Market data source types"""
    GPU_METRICS = "gpu_metrics"
    BOOKING_DATA = "booking_data"
    REGIONAL_DEMAND = "regional_demand"
    COMPETITOR_PRICES = "competitor_prices"
    PERFORMANCE_DATA = "performance_data"
    MARKET_SENTIMENT = "market_sentiment"


@dataclass
class MarketDataPoint:
    """Single market data point"""
    source: DataSource
    resource_id: str
    resource_type: str
    region: str
    timestamp: datetime
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMarketData:
    """Aggregated market data for a resource type and region"""
    resource_type: str
    region: str
    timestamp: datetime
    demand_level: float
    supply_level: float
    average_price: float
    price_volatility: float
    utilization_rate: float
    competitor_prices: List[float]
    market_sentiment: float
    data_sources: List[DataSource] = field(default_factory=list)
    confidence_score: float = 0.8


class MarketDataCollector:
    """Collects and processes market data from multiple sources"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_callbacks: Dict[DataSource, List[Callable]] = {}
        self.raw_data: List[MarketDataPoint] = []
        self.aggregated_data: Dict[str, AggregatedMarketData] = {}
        self.websocket_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        
        # Data collection intervals (seconds)
        self.collection_intervals = {
            DataSource.GPU_METRICS: 60,      # 1 minute
            DataSource.BOOKING_DATA: 30,    # 30 seconds
            DataSource.REGIONAL_DEMAND: 300, # 5 minutes
            DataSource.COMPETITOR_PRICES: 600,  # 10 minutes
            DataSource.PERFORMANCE_DATA: 120,   # 2 minutes
            DataSource.MARKET_SENTIMENT: 180    # 3 minutes
        }
        
        # Data retention
        self.max_data_age = timedelta(hours=48)
        self.max_raw_data_points = 10000
        
        # WebSocket server
        self.websocket_port = config.get("websocket_port", 8765)
        self.websocket_server = None
        
    async def initialize(self):
        """Initialize the market data collector"""
        logger.info("Initializing Market Data Collector")
        
        # Start data collection tasks
        for source in DataSource:
            asyncio.create_task(self._collect_data_source(source))
        
        # Start data aggregation task
        asyncio.create_task(self._aggregate_market_data())
        
        # Start data cleanup task
        asyncio.create_task(self._cleanup_old_data())
        
        # Start WebSocket server for real-time updates
        await self._start_websocket_server()
        
        logger.info("Market Data Collector initialized")
    
    def register_callback(self, source: DataSource, callback: Callable):
        """Register callback for data updates"""
        if source not in self.data_callbacks:
            self.data_callbacks[source] = []
        self.data_callbacks[source].append(callback)
        logger.info(f"Registered callback for {source.value}")
    
    async def get_aggregated_data(
        self,
        resource_type: str,
        region: str = "global"
    ) -> Optional[AggregatedMarketData]:
        """Get aggregated market data for a resource type and region"""
        
        key = f"{resource_type}_{region}"
        return self.aggregated_data.get(key)
    
    async def get_recent_data(
        self,
        source: DataSource,
        minutes: int = 60
    ) -> List[MarketDataPoint]:
        """Get recent data from a specific source"""
        
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        return [
            point for point in self.raw_data
            if point.source == source and point.timestamp >= cutoff_time
        ]
    
    async def _collect_data_source(self, source: DataSource):
        """Collect data from a specific source"""
        
        interval = self.collection_intervals[source]
        
        while True:
            try:
                await self._collect_from_source(source)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error collecting data from {source.value}: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _collect_from_source(self, source: DataSource):
        """Collect data from a specific source"""
        
        if source == DataSource.GPU_METRICS:
            await self._collect_gpu_metrics()
        elif source == DataSource.BOOKING_DATA:
            await self._collect_booking_data()
        elif source == DataSource.REGIONAL_DEMAND:
            await self._collect_regional_demand()
        elif source == DataSource.COMPETITOR_PRICES:
            await self._collect_competitor_prices()
        elif source == DataSource.PERFORMANCE_DATA:
            await self._collect_performance_data()
        elif source == DataSource.MARKET_SENTIMENT:
            await self._collect_market_sentiment()
    
    async def _collect_gpu_metrics(self):
        """Collect GPU utilization and performance metrics"""
        
        try:
            # In a real implementation, this would query GPU monitoring systems
            # For now, simulate data collection
            
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate GPU metrics
                utilization = 0.6 + (hash(region + str(datetime.utcnow().minute)) % 100) / 200
                available_gpus = 100 + (hash(region + str(datetime.utcnow().hour)) % 50)
                total_gpus = 150
                
                supply_level = available_gpus / total_gpus
                
                # Create data points
                data_point = MarketDataPoint(
                    source=DataSource.GPU_METRICS,
                    resource_id=f"gpu_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=utilization,
                    metadata={
                        "available_gpus": available_gpus,
                        "total_gpus": total_gpus,
                        "supply_level": supply_level
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting GPU metrics: {e}")
    
    async def _collect_booking_data(self):
        """Collect booking and transaction data"""
        
        try:
            # Simulate booking data collection
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate recent bookings
                recent_bookings = (hash(region + str(datetime.utcnow().minute)) % 20)
                total_capacity = 100
                booking_rate = recent_bookings / total_capacity
                
                # Calculate demand level from booking rate
                demand_level = min(1.0, booking_rate * 2)
                
                data_point = MarketDataPoint(
                    source=DataSource.BOOKING_DATA,
                    resource_id=f"bookings_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=booking_rate,
                    metadata={
                        "recent_bookings": recent_bookings,
                        "total_capacity": total_capacity,
                        "demand_level": demand_level
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting booking data: {e}")
    
    async def _collect_regional_demand(self):
        """Collect regional demand patterns"""
        
        try:
            # Simulate regional demand analysis
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate demand based on time of day and region
                hour = datetime.utcnow().hour
                
                # Different regions have different peak times
                if region == "asia":
                    peak_hours = [9, 10, 11, 14, 15, 16]  # Business hours Asia
                elif region == "europe":
                    peak_hours = [8, 9, 10, 11, 14, 15, 16]  # Business hours Europe
                elif region == "us_east":
                    peak_hours = [9, 10, 11, 14, 15, 16, 17]  # Business hours US East
                else:  # us_west
                    peak_hours = [10, 11, 12, 14, 15, 16, 17]  # Business hours US West
                
                base_demand = 0.4
                if hour in peak_hours:
                    demand_multiplier = 1.5
                elif hour in [h + 1 for h in peak_hours] or hour in [h - 1 for h in peak_hours]:
                    demand_multiplier = 1.2
                else:
                    demand_multiplier = 0.8
                
                demand_level = min(1.0, base_demand * demand_multiplier)
                
                data_point = MarketDataPoint(
                    source=DataSource.REGIONAL_DEMAND,
                    resource_id=f"demand_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=demand_level,
                    metadata={
                        "hour": hour,
                        "peak_hours": peak_hours,
                        "demand_multiplier": demand_multiplier
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting regional demand: {e}")
    
    async def _collect_competitor_prices(self):
        """Collect competitor pricing data"""
        
        try:
            # Simulate competitor price monitoring
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate competitor prices
                base_price = 0.05
                competitor_prices = [
                    base_price * (1 + (hash(f"comp1_{region}") % 20 - 10) / 100),
                    base_price * (1 + (hash(f"comp2_{region}") % 20 - 10) / 100),
                    base_price * (1 + (hash(f"comp3_{region}") % 20 - 10) / 100),
                    base_price * (1 + (hash(f"comp4_{region}") % 20 - 10) / 100)
                ]
                
                avg_competitor_price = sum(competitor_prices) / len(competitor_prices)
                
                data_point = MarketDataPoint(
                    source=DataSource.COMPETITOR_PRICES,
                    resource_id=f"competitors_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=avg_competitor_price,
                    metadata={
                        "competitor_prices": competitor_prices,
                        "price_count": len(competitor_prices)
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting competitor prices: {e}")
    
    async def _collect_performance_data(self):
        """Collect provider performance metrics"""
        
        try:
            # Simulate performance data collection
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate performance metrics
                completion_rate = 0.85 + (hash(f"perf_{region}") % 20) / 200
                average_response_time = 120 + (hash(f"resp_{region}") % 60)  # seconds
                error_rate = 0.02 + (hash(f"error_{region}") % 10) / 1000
                
                performance_score = completion_rate * (1 - error_rate)
                
                data_point = MarketDataPoint(
                    source=DataSource.PERFORMANCE_DATA,
                    resource_id=f"performance_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=performance_score,
                    metadata={
                        "completion_rate": completion_rate,
                        "average_response_time": average_response_time,
                        "error_rate": error_rate
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting performance data: {e}")
    
    async def _collect_market_sentiment(self):
        """Collect market sentiment data"""
        
        try:
            # Simulate sentiment analysis
            regions = ["us_west", "us_east", "europe", "asia"]
            
            for region in regions:
                # Simulate sentiment based on recent market activity
                recent_activity = (hash(f"activity_{region}") % 100) / 100
                price_trend = (hash(f"trend_{region}") % 21 - 10) / 100  # -0.1 to 0.1
                volume_change = (hash(f"volume_{region}") % 31 - 15) / 100  # -0.15 to 0.15
                
                # Calculate sentiment score (-1 to 1)
                sentiment = (recent_activity * 0.4 + price_trend * 0.3 + volume_change * 0.3)
                sentiment = max(-1.0, min(1.0, sentiment))
                
                data_point = MarketDataPoint(
                    source=DataSource.MARKET_SENTIMENT,
                    resource_id=f"sentiment_{region}",
                    resource_type="gpu",
                    region=region,
                    timestamp=datetime.utcnow(),
                    value=sentiment,
                    metadata={
                        "recent_activity": recent_activity,
                        "price_trend": price_trend,
                        "volume_change": volume_change
                    }
                )
                
                await self._add_data_point(data_point)
                
        except Exception as e:
            logger.error(f"Error collecting market sentiment: {e}")
    
    async def _add_data_point(self, data_point: MarketDataPoint):
        """Add a data point and notify callbacks"""
        
        # Add to raw data
        self.raw_data.append(data_point)
        
        # Maintain data size limits
        if len(self.raw_data) > self.max_raw_data_points:
            self.raw_data = self.raw_data[-self.max_raw_data_points:]
        
        # Notify callbacks
        if data_point.source in self.data_callbacks:
            for callback in self.data_callbacks[data_point.source]:
                try:
                    await callback(data_point)
                except Exception as e:
                    logger.error(f"Error in data callback: {e}")
        
        # Broadcast via WebSocket
        await self._broadcast_data_point(data_point)
    
    async def _aggregate_market_data(self):
        """Aggregate raw market data into useful metrics"""
        
        while True:
            try:
                await self._perform_aggregation()
                await asyncio.sleep(60)  # Aggregate every minute
            except Exception as e:
                logger.error(f"Error aggregating market data: {e}")
                await asyncio.sleep(30)
    
    async def _perform_aggregation(self):
        """Perform the actual data aggregation"""
        
        regions = ["us_west", "us_east", "europe", "asia", "global"]
        resource_types = ["gpu", "service", "storage"]
        
        for resource_type in resource_types:
            for region in regions:
                aggregated = await self._aggregate_for_resource_region(resource_type, region)
                if aggregated:
                    key = f"{resource_type}_{region}"
                    self.aggregated_data[key] = aggregated
    
    async def _aggregate_for_resource_region(
        self,
        resource_type: str,
        region: str
    ) -> Optional[AggregatedMarketData]:
        """Aggregate data for a specific resource type and region"""
        
        try:
            # Get recent data for this resource type and region
            cutoff_time = datetime.utcnow() - timedelta(minutes=30)
            relevant_data = [
                point for point in self.raw_data
                if (point.resource_type == resource_type and 
                    point.region == region and 
                    point.timestamp >= cutoff_time)
            ]
            
            if not relevant_data:
                return None
            
            # Aggregate metrics by source
            source_data = {}
            data_sources = []
            
            for point in relevant_data:
                if point.source not in source_data:
                    source_data[point.source] = []
                source_data[point.source].append(point)
                if point.source not in data_sources:
                    data_sources.append(point.source)
            
            # Calculate aggregated metrics
            demand_level = self._calculate_aggregated_demand(source_data)
            supply_level = self._calculate_aggregated_supply(source_data)
            average_price = self._calculate_aggregated_price(source_data)
            price_volatility = self._calculate_price_volatility(source_data)
            utilization_rate = self._calculate_aggregated_utilization(source_data)
            competitor_prices = self._get_competitor_prices(source_data)
            market_sentiment = self._calculate_aggregated_sentiment(source_data)
            
            # Calculate confidence score based on data freshness and completeness
            confidence = self._calculate_aggregation_confidence(source_data, data_sources)
            
            return AggregatedMarketData(
                resource_type=resource_type,
                region=region,
                timestamp=datetime.utcnow(),
                demand_level=demand_level,
                supply_level=supply_level,
                average_price=average_price,
                price_volatility=price_volatility,
                utilization_rate=utilization_rate,
                competitor_prices=competitor_prices,
                market_sentiment=market_sentiment,
                data_sources=data_sources,
                confidence_score=confidence
            )
            
        except Exception as e:
            logger.error(f"Error aggregating data for {resource_type}_{region}: {e}")
            return None
    
    def _calculate_aggregated_demand(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate aggregated demand level"""
        
        demand_values = []
        
        # Get demand from booking data
        if DataSource.BOOKING_DATA in source_data:
            for point in source_data[DataSource.BOOKING_DATA]:
                if "demand_level" in point.metadata:
                    demand_values.append(point.metadata["demand_level"])
        
        # Get demand from regional demand data
        if DataSource.REGIONAL_DEMAND in source_data:
            for point in source_data[DataSource.REGIONAL_DEMAND]:
                demand_values.append(point.value)
        
        if demand_values:
            return sum(demand_values) / len(demand_values)
        else:
            return 0.5  # Default
    
    def _calculate_aggregated_supply(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate aggregated supply level"""
        
        supply_values = []
        
        # Get supply from GPU metrics
        if DataSource.GPU_METRICS in source_data:
            for point in source_data[DataSource.GPU_METRICS]:
                if "supply_level" in point.metadata:
                    supply_values.append(point.metadata["supply_level"])
        
        if supply_values:
            return sum(supply_values) / len(supply_values)
        else:
            return 0.5  # Default
    
    def _calculate_aggregated_price(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate aggregated average price"""
        
        price_values = []
        
        # Get prices from competitor data
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                price_values.append(point.value)
        
        if price_values:
            return sum(price_values) / len(price_values)
        else:
            return 0.05  # Default price
    
    def _calculate_price_volatility(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate price volatility"""
        
        price_values = []
        
        # Get historical prices from competitor data
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                if "competitor_prices" in point.metadata:
                    price_values.extend(point.metadata["competitor_prices"])
        
        if len(price_values) >= 2:
            import numpy as np
            mean_price = sum(price_values) / len(price_values)
            variance = sum((p - mean_price) ** 2 for p in price_values) / len(price_values)
            volatility = (variance ** 0.5) / mean_price if mean_price > 0 else 0
            return min(1.0, volatility)
        else:
            return 0.1  # Default volatility
    
    def _calculate_aggregated_utilization(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate aggregated utilization rate"""
        
        utilization_values = []
        
        # Get utilization from GPU metrics
        if DataSource.GPU_METRICS in source_data:
            for point in source_data[DataSource.GPU_METRICS]:
                utilization_values.append(point.value)
        
        if utilization_values:
            return sum(utilization_values) / len(utilization_values)
        else:
            return 0.6  # Default utilization
    
    def _get_competitor_prices(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> List[float]:
        """Get competitor prices"""
        
        competitor_prices = []
        
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                if "competitor_prices" in point.metadata:
                    competitor_prices.extend(point.metadata["competitor_prices"])
        
        return competitor_prices[:10]  # Limit to 10 most recent prices
    
    def _calculate_aggregated_sentiment(self, source_data: Dict[DataSource, List[MarketDataPoint]]) -> float:
        """Calculate aggregated market sentiment"""
        
        sentiment_values = []
        
        # Get sentiment from market sentiment data
        if DataSource.MARKET_SENTIMENT in source_data:
            for point in source_data[DataSource.MARKET_SENTIMENT]:
                sentiment_values.append(point.value)
        
        if sentiment_values:
            return sum(sentiment_values) / len(sentiment_values)
        else:
            return 0.0  # Neutral sentiment
    
    def _calculate_aggregation_confidence(
        self,
        source_data: Dict[DataSource, List[MarketDataPoint]],
        data_sources: List[DataSource]
    ) -> float:
        """Calculate confidence score for aggregated data"""
        
        # Base confidence from number of data sources
        source_confidence = min(1.0, len(data_sources) / 4.0)  # 4 sources available
        
        # Data freshness confidence
        now = datetime.utcnow()
        freshness_scores = []
        
        for source, points in source_data.items():
            if points:
                latest_time = max(point.timestamp for point in points)
                age_minutes = (now - latest_time).total_seconds() / 60
                freshness_score = max(0.0, 1.0 - age_minutes / 60)  # Decay over 1 hour
                freshness_scores.append(freshness_score)
        
        freshness_confidence = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.5
        
        # Data volume confidence
        total_points = sum(len(points) for points in source_data.values())
        volume_confidence = min(1.0, total_points / 20.0)  # 20 points = full confidence
        
        # Combine confidences
        overall_confidence = (
            source_confidence * 0.4 +
            freshness_confidence * 0.4 +
            volume_confidence * 0.2
        )
        
        return max(0.1, min(0.95, overall_confidence))
    
    async def _cleanup_old_data(self):
        """Clean up old data points"""
        
        while True:
            try:
                cutoff_time = datetime.utcnow() - self.max_data_age
                
                # Remove old raw data
                self.raw_data = [
                    point for point in self.raw_data
                    if point.timestamp >= cutoff_time
                ]
                
                # Remove old aggregated data
                for key in list(self.aggregated_data.keys()):
                    if self.aggregated_data[key].timestamp < cutoff_time:
                        del self.aggregated_data[key]
                
                await asyncio.sleep(3600)  # Clean up every hour
            except Exception as e:
                logger.error(f"Error cleaning up old data: {e}")
                await asyncio.sleep(300)
    
    async def _start_websocket_server(self):
        """Start WebSocket server for real-time data streaming"""
        
        async def handle_websocket(websocket, path):
            """Handle WebSocket connections"""
            try:
                # Store connection
                connection_id = f"{websocket.remote_address}_{datetime.utcnow().timestamp()}"
                self.websocket_connections[connection_id] = websocket
                
                logger.info(f"WebSocket client connected: {connection_id}")
                
                # Keep connection alive
                try:
                    async for message in websocket:
                        # Handle client messages if needed
                        pass
                except websockets.exceptions.ConnectionClosed:
                    pass
                finally:
                    # Remove connection
                    if connection_id in self.websocket_connections:
                        del self.websocket_connections[connection_id]
                    logger.info(f"WebSocket client disconnected: {connection_id}")
                    
            except Exception as e:
                logger.error(f"Error handling WebSocket connection: {e}")
        
        try:
            self.websocket_server = await websockets.serve(
                handle_websocket,
                "localhost",
                self.websocket_port
            )
            logger.info(f"WebSocket server started on port {self.websocket_port}")
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
    
    async def _broadcast_data_point(self, data_point: MarketDataPoint):
        """Broadcast data point to all connected WebSocket clients"""
        
        if not self.websocket_connections:
            return
        
        message = {
            "type": "market_data",
            "source": data_point.source.value,
            "resource_id": data_point.resource_id,
            "resource_type": data_point.resource_type,
            "region": data_point.region,
            "timestamp": data_point.timestamp.isoformat(),
            "value": data_point.value,
            "metadata": data_point.metadata
        }
        
        message_str = json.dumps(message)
        
        # Send to all connected clients
        disconnected = []
        for connection_id, websocket in self.websocket_connections.items():
            try:
                await websocket.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                disconnected.append(connection_id)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                disconnected.append(connection_id)
        
        # Remove disconnected clients
        for connection_id in disconnected:
            if connection_id in self.websocket_connections:
                del self.websocket_connections[connection_id]
