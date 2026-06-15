"""
Market Data Collector for Dynamic Pricing Engine
Collects real-time market data from various sources for pricing calculations
"""
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol  # type: ignore[attr-defined]

from aitbc import get_logger

logger = get_logger(__name__)

class DataSource(StrEnum):
    """Market data source types"""
    GPU_METRICS = 'gpu_metrics'
    BOOKING_DATA = 'booking_data'
    REGIONAL_DEMAND = 'regional_demand'
    COMPETITOR_PRICES = 'competitor_prices'
    PERFORMANCE_DATA = 'performance_data'
    MARKET_SENTIMENT = 'market_sentiment'

@dataclass
class MarketDataPoint:
    """Single market data point"""
    source: DataSource
    resource_id: str
    resource_type: str
    region: str
    timestamp: datetime
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)

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
    competitor_prices: list[float]
    market_sentiment: float
    data_sources: list[DataSource] = field(default_factory=list)
    confidence_score: float = 0.8

class MarketDataCollector:
    """Collects and processes market data from multiple sources"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.data_callbacks: dict[DataSource, list[Callable]] = {}
        self.raw_data: list[MarketDataPoint] = []
        self.aggregated_data: dict[str, AggregatedMarketData] = {}
        self.websocket_connections: dict[str, WebSocketServerProtocol] = {}
        self.collection_intervals = {DataSource.GPU_METRICS: 60, DataSource.BOOKING_DATA: 30, DataSource.REGIONAL_DEMAND: 300, DataSource.COMPETITOR_PRICES: 600, DataSource.PERFORMANCE_DATA: 120, DataSource.MARKET_SENTIMENT: 180}
        self.max_data_age = timedelta(hours=48)
        self.max_raw_data_points = 10000
        self.websocket_port = config.get('websocket_port', 8765)
        self.websocket_server = None

    async def initialize(self) -> None:
        """Initialize the market data collector"""
        logger.info('Initializing Market Data Collector')
        for source in DataSource:
            asyncio.create_task(self._collect_data_source(source))
        asyncio.create_task(self._aggregate_market_data())
        asyncio.create_task(self._cleanup_old_data())
        await self._start_websocket_server()
        logger.info('Market Data Collector initialized')

    def register_callback(self, source: DataSource, callback: Callable) -> None:
        """Register callback for data updates"""
        if source not in self.data_callbacks:
            self.data_callbacks[source] = []
        self.data_callbacks[source].append(callback)
        logger.info('Registered callback for %s', source.value)

    async def get_aggregated_data(self, resource_type: str, region: str='global') -> AggregatedMarketData | None:
        """Get aggregated market data for a resource type and region"""
        key = f'{resource_type}_{region}'
        return self.aggregated_data.get(key)

    async def get_recent_data(self, source: DataSource, minutes: int=60) -> list[MarketDataPoint]:
        """Get recent data from a specific source"""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=minutes)
        return [point for point in self.raw_data if point.source == source and point.timestamp >= cutoff_time]

    async def _collect_data_source(self, source: DataSource) -> None:
        """Collect data from a specific source"""
        interval = self.collection_intervals[source]
        while True:
            try:
                await self._collect_from_source(source)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error('Error collecting data from %s: %s', source.value, e)
                await asyncio.sleep(60)

    async def _collect_from_source(self, source: DataSource) -> None:
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

    async def _collect_gpu_metrics(self) -> None:
        """Collect GPU utilization and performance metrics"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                utilization = 0.6 + hash(region + str(datetime.now(UTC).minute)) % 100 / 200
                available_gpus = 100 + hash(region + str(datetime.now(UTC).hour)) % 50
                total_gpus = 150
                supply_level = available_gpus / total_gpus
                data_point = MarketDataPoint(source=DataSource.GPU_METRICS, resource_id=f'gpu_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=utilization, metadata={'available_gpus': available_gpus, 'total_gpus': total_gpus, 'supply_level': supply_level})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting GPU metrics: %s', e)

    async def _collect_booking_data(self) -> None:
        """Collect booking and transaction data"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                recent_bookings = hash(region + str(datetime.now(UTC).minute)) % 20
                total_capacity = 100
                booking_rate = recent_bookings / total_capacity
                demand_level = min(1.0, booking_rate * 2)
                data_point = MarketDataPoint(source=DataSource.BOOKING_DATA, resource_id=f'bookings_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=booking_rate, metadata={'recent_bookings': recent_bookings, 'total_capacity': total_capacity, 'demand_level': demand_level})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting booking data: %s', e)

    async def _collect_regional_demand(self) -> None:
        """Collect regional demand patterns"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                hour = datetime.now(UTC).hour
                if region == 'asia':
                    peak_hours = [9, 10, 11, 14, 15, 16]
                elif region == 'europe':
                    peak_hours = [8, 9, 10, 11, 14, 15, 16]
                elif region == 'us_east':
                    peak_hours = [9, 10, 11, 14, 15, 16, 17]
                else:
                    peak_hours = [10, 11, 12, 14, 15, 16, 17]
                base_demand = 0.4
                if hour in peak_hours:
                    demand_multiplier = 1.5
                elif hour in [h + 1 for h in peak_hours] or hour in [h - 1 for h in peak_hours]:
                    demand_multiplier = 1.2
                else:
                    demand_multiplier = 0.8
                demand_level = min(1.0, base_demand * demand_multiplier)
                data_point = MarketDataPoint(source=DataSource.REGIONAL_DEMAND, resource_id=f'demand_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=demand_level, metadata={'hour': hour, 'peak_hours': peak_hours, 'demand_multiplier': demand_multiplier})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting regional demand: %s', e)

    async def _collect_competitor_prices(self) -> None:
        """Collect competitor pricing data"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                base_price = 0.05
                competitor_prices = [base_price * (1 + (hash(f'comp1_{region}') % 20 - 10) / 100), base_price * (1 + (hash(f'comp2_{region}') % 20 - 10) / 100), base_price * (1 + (hash(f'comp3_{region}') % 20 - 10) / 100), base_price * (1 + (hash(f'comp4_{region}') % 20 - 10) / 100)]
                avg_competitor_price = sum(competitor_prices) / len(competitor_prices)
                data_point = MarketDataPoint(source=DataSource.COMPETITOR_PRICES, resource_id=f'competitors_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=avg_competitor_price, metadata={'competitor_prices': competitor_prices, 'price_count': len(competitor_prices)})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting competitor prices: %s', e)

    async def _collect_performance_data(self) -> None:
        """Collect provider performance metrics"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                completion_rate = 0.85 + hash(f'perf_{region}') % 20 / 200
                average_response_time = 120 + hash(f'resp_{region}') % 60
                error_rate = 0.02 + hash(f'error_{region}') % 10 / 1000
                performance_score = completion_rate * (1 - error_rate)
                data_point = MarketDataPoint(source=DataSource.PERFORMANCE_DATA, resource_id=f'performance_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=performance_score, metadata={'completion_rate': completion_rate, 'average_response_time': average_response_time, 'error_rate': error_rate})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting performance data: %s', e)

    async def _collect_market_sentiment(self) -> None:
        """Collect market sentiment data"""
        try:
            regions = ['us_west', 'us_east', 'europe', 'asia']
            for region in regions:
                recent_activity = hash(f'activity_{region}') % 100 / 100
                price_trend = (hash(f'trend_{region}') % 21 - 10) / 100
                volume_change = (hash(f'volume_{region}') % 31 - 15) / 100
                sentiment = recent_activity * 0.4 + price_trend * 0.3 + volume_change * 0.3
                sentiment = max(-1.0, min(1.0, sentiment))
                data_point = MarketDataPoint(source=DataSource.MARKET_SENTIMENT, resource_id=f'sentiment_{region}', resource_type='gpu', region=region, timestamp=datetime.now(UTC), value=sentiment, metadata={'recent_activity': recent_activity, 'price_trend': price_trend, 'volume_change': volume_change})
                await self._add_data_point(data_point)
        except Exception as e:
            logger.error('Error collecting market sentiment: %s', e)

    async def _add_data_point(self, data_point: MarketDataPoint) -> None:
        """Add a data point and notify callbacks"""
        self.raw_data.append(data_point)
        if len(self.raw_data) > self.max_raw_data_points:
            self.raw_data = self.raw_data[-self.max_raw_data_points:]
        if data_point.source in self.data_callbacks:
            for callback in self.data_callbacks[data_point.source]:
                try:
                    await callback(data_point)
                except Exception as e:
                    logger.error('Error in data callback: %s', e)
        await self._broadcast_data_point(data_point)

    async def _aggregate_market_data(self) -> None:
        """Aggregate raw market data into useful metrics"""
        while True:
            try:
                await self._perform_aggregation()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error('Error aggregating market data: %s', e)
                await asyncio.sleep(30)

    async def _perform_aggregation(self) -> None:
        """Perform the actual data aggregation"""
        regions = ['us_west', 'us_east', 'europe', 'asia', 'global']
        resource_types = ['gpu', 'service', 'storage']
        for resource_type in resource_types:
            for region in regions:
                aggregated = await self._aggregate_for_resource_region(resource_type, region)
                if aggregated:
                    key = f'{resource_type}_{region}'
                    self.aggregated_data[key] = aggregated

    async def _aggregate_for_resource_region(self, resource_type: str, region: str) -> AggregatedMarketData | None:
        """Aggregate data for a specific resource type and region"""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(minutes=30)
            relevant_data = [point for point in self.raw_data if point.resource_type == resource_type and point.region == region and (point.timestamp >= cutoff_time)]
            if not relevant_data:
                return None
            source_data: dict[str, list[Any]] = {}
            data_sources = []
            for point in relevant_data:
                if point.source not in source_data:
                    source_data[point.source] = []
                source_data[point.source].append(point)
                if point.source not in data_sources:
                    data_sources.append(point.source)
            demand_level = self._calculate_aggregated_demand(source_data)  # type: ignore[arg-type]
            supply_level = self._calculate_aggregated_supply(source_data)  # type: ignore[arg-type]
            average_price = self._calculate_aggregated_price(source_data)  # type: ignore[arg-type]
            price_volatility = self._calculate_price_volatility(source_data)  # type: ignore[arg-type]
            utilization_rate = self._calculate_aggregated_utilization(source_data)  # type: ignore[arg-type]
            competitor_prices = self._get_competitor_prices(source_data)  # type: ignore[arg-type]
            market_sentiment = self._calculate_aggregated_sentiment(source_data)  # type: ignore[arg-type]
            confidence = self._calculate_aggregation_confidence(source_data, data_sources)  # type: ignore[arg-type]
            return AggregatedMarketData(resource_type=resource_type, region=region, timestamp=datetime.now(UTC), demand_level=demand_level, supply_level=supply_level, average_price=average_price, price_volatility=price_volatility, utilization_rate=utilization_rate, competitor_prices=competitor_prices, market_sentiment=market_sentiment, data_sources=data_sources, confidence_score=confidence)
        except Exception as e:
            logger.error('Error aggregating data for %s_%s: %s', resource_type, region, e)
            return None

    def _calculate_aggregated_demand(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate aggregated demand level"""
        demand_values = []
        if DataSource.BOOKING_DATA in source_data:
            for point in source_data[DataSource.BOOKING_DATA]:
                if 'demand_level' in point.metadata:
                    demand_values.append(point.metadata['demand_level'])
        if DataSource.REGIONAL_DEMAND in source_data:
            for point in source_data[DataSource.REGIONAL_DEMAND]:
                demand_values.append(point.value)
        if demand_values:
            return sum(demand_values) / len(demand_values)  # type: ignore[no-any-return]
        else:
            return 0.5

    def _calculate_aggregated_supply(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate aggregated supply level"""
        supply_values = []
        if DataSource.GPU_METRICS in source_data:
            for point in source_data[DataSource.GPU_METRICS]:
                if 'supply_level' in point.metadata:
                    supply_values.append(point.metadata['supply_level'])
        if supply_values:
            return sum(supply_values) / len(supply_values)  # type: ignore[no-any-return]
        else:
            return 0.5

    def _calculate_aggregated_price(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate aggregated average price"""
        price_values = []
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                price_values.append(point.value)
        if price_values:
            return sum(price_values) / len(price_values)
        else:
            return 0.05

    def _calculate_price_volatility(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate price volatility"""
        price_values = []
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                if 'competitor_prices' in point.metadata:
                    price_values.extend(point.metadata['competitor_prices'])
        if len(price_values) >= 2:
            mean_price = sum(price_values) / len(price_values)
            variance = sum((p - mean_price) ** 2 for p in price_values) / len(price_values)
            volatility = variance ** 0.5 / mean_price if mean_price > 0 else 0
            return min(1.0, volatility)
        else:
            return 0.1

    def _calculate_aggregated_utilization(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate aggregated utilization rate"""
        utilization_values = []
        if DataSource.GPU_METRICS in source_data:
            for point in source_data[DataSource.GPU_METRICS]:
                utilization_values.append(point.value)
        if utilization_values:
            return sum(utilization_values) / len(utilization_values)
        else:
            return 0.6

    def _get_competitor_prices(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> list[float]:
        """Get competitor prices"""
        competitor_prices = []
        if DataSource.COMPETITOR_PRICES in source_data:
            for point in source_data[DataSource.COMPETITOR_PRICES]:
                if 'competitor_prices' in point.metadata:
                    competitor_prices.extend(point.metadata['competitor_prices'])
        return competitor_prices[:10]

    def _calculate_aggregated_sentiment(self, source_data: dict[DataSource, list[MarketDataPoint]]) -> float:
        """Calculate aggregated market sentiment"""
        sentiment_values = []
        if DataSource.MARKET_SENTIMENT in source_data:
            for point in source_data[DataSource.MARKET_SENTIMENT]:
                sentiment_values.append(point.value)
        if sentiment_values:
            return sum(sentiment_values) / len(sentiment_values)
        else:
            return 0.0

    def _calculate_aggregation_confidence(self, source_data: dict[DataSource, list[MarketDataPoint]], data_sources: list[DataSource]) -> float:
        """Calculate confidence score for aggregated data"""
        source_confidence = min(1.0, len(data_sources) / 4.0)
        now = datetime.now(UTC)
        freshness_scores = []
        for _source, points in source_data.items():
            if points:
                latest_time = max(point.timestamp for point in points)
                age_minutes = (now - latest_time).total_seconds() / 60
                freshness_score = max(0.0, 1.0 - age_minutes / 60)
                freshness_scores.append(freshness_score)
        freshness_confidence = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.5
        total_points = sum(len(points) for points in source_data.values())
        volume_confidence = min(1.0, total_points / 20.0)
        overall_confidence = source_confidence * 0.4 + freshness_confidence * 0.4 + volume_confidence * 0.2
        return max(0.1, min(0.95, overall_confidence))

    async def _cleanup_old_data(self) -> None:
        """Clean up old data points"""
        while True:
            try:
                cutoff_time = datetime.now(UTC) - self.max_data_age
                self.raw_data = [point for point in self.raw_data if point.timestamp >= cutoff_time]
                for key in list(self.aggregated_data.keys()):
                    if self.aggregated_data[key].timestamp < cutoff_time:
                        del self.aggregated_data[key]
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error('Error cleaning up old data: %s', e)
                await asyncio.sleep(300)

    async def _start_websocket_server(self) -> None:
        """Start WebSocket server for real-time data streaming"""

        async def handle_websocket(websocket: Any, path: str) -> None:
            """Handle WebSocket connections"""
            try:
                connection_id = f'{websocket.remote_address}_{datetime.now(UTC).timestamp()}'
                self.websocket_connections[connection_id] = websocket
                logger.info('WebSocket client connected: %s', connection_id)
                try:
                    async for _message in websocket:
                        pass
                except websockets.exceptions.ConnectionClosed:
                    pass
                finally:
                    if connection_id in self.websocket_connections:
                        del self.websocket_connections[connection_id]
                    logger.info('WebSocket client disconnected: %s', connection_id)
            except Exception as e:
                logger.error('Error handling WebSocket connection: %s', e)
        try:
            self.websocket_server = await websockets.serve(handle_websocket, 'localhost', self.websocket_port)  # type: ignore[assignment, arg-type]
            logger.info('WebSocket server started on port %s', self.websocket_port)
        except Exception as e:
            logger.error('Failed to start WebSocket server: %s', e)

    async def _broadcast_data_point(self, data_point: MarketDataPoint) -> None:
        """Broadcast data point to all connected WebSocket clients"""
        if not self.websocket_connections:
            return
        message = {'type': 'market_data', 'source': data_point.source.value, 'resource_id': data_point.resource_id, 'resource_type': data_point.resource_type, 'region': data_point.region, 'timestamp': data_point.timestamp.isoformat(), 'value': data_point.value, 'metadata': data_point.metadata}
        message_str = json.dumps(message)
        disconnected = []
        for connection_id, websocket in self.websocket_connections.items():
            try:
                await websocket.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                disconnected.append(connection_id)
            except Exception as e:
                logger.error('Error sending WebSocket message: %s', e)
                disconnected.append(connection_id)
        for connection_id in disconnected:
            if connection_id in self.websocket_connections:
                del self.websocket_connections[connection_id]
