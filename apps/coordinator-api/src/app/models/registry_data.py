"""
Data analytics service definitions
"""

from typing import Dict, List, Any, Union
from .registry import (
    ServiceDefinition,
    ServiceCategory,
    ParameterDefinition,
    ParameterType,
    HardwareRequirement,
    PricingTier,
    PricingModel
)


DATA_ANALYTICS_SERVICES = {
    "big_data_processing": ServiceDefinition(
        id="big_data_processing",
        name="Big Data Processing",
        category=ServiceCategory.DATA_ANALYTICS,
        description="GPU-accelerated ETL and data processing with RAPIDS",
        icon="📊",
        input_parameters=[
            ParameterDefinition(
                name="operation",
                type=ParameterType.ENUM,
                required=True,
                description="Processing operation",
                options=["etl", "aggregate", "join", "filter", "transform", "clean"]
            ),
            ParameterDefinition(
                name="data_source",
                type=ParameterType.STRING,
                required=True,
                description="Data source URL or connection string"
            ),
            ParameterDefinition(
                name="query",
                type=ParameterType.STRING,
                required=True,
                description="SQL or data processing query"
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=False,
                description="Output format",
                default="parquet",
                options=["parquet", "csv", "json", "delta", "orc"]
            ),
            ParameterDefinition(
                name="partition_by",
                type=ParameterType.ARRAY,
                required=False,
                description="Partition columns",
                items={"type": "string"}
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "output_url": {"type": "string"},
                "row_count": {"type": "integer"},
                "columns": {"type": "array"},
                "processing_stats": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="ram", min_value=32, recommended=128, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=1000, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_gb", model=PricingModel.PER_GB, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1),
            PricingTier(name="enterprise", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.5)
        ],
        capabilities=["gpu-sql", "etl", "streaming", "distributed"],
        tags=["bigdata", "etl", "rapids", "spark", "sql"],
        max_concurrent=5,
        timeout_seconds=3600
    ),
    
    "real_time_analytics": ServiceDefinition(
        id="real_time_analytics",
        name="Real-time Analytics",
        category=ServiceCategory.DATA_ANALYTICS,
        description="Stream processing and real-time analytics with GPU acceleration",
        icon="⚡",
        input_parameters=[
            ParameterDefinition(
                name="stream_source",
                type=ParameterType.STRING,
                required=True,
                description="Stream source (Kafka, Kinesis, etc.)"
            ),
            ParameterDefinition(
                name="query",
                type=ParameterType.STRING,
                required=True,
                description="Stream processing query"
            ),
            ParameterDefinition(
                name="window_size",
                type=ParameterType.STRING,
                required=False,
                description="Window size (e.g., 1m, 5m, 1h)",
                default="5m"
            ),
            ParameterDefinition(
                name="aggregations",
                type=ParameterType.ARRAY,
                required=True,
                description="Aggregation functions",
                items={"type": "string"}
            ),
            ParameterDefinition(
                name="output_sink",
                type=ParameterType.STRING,
                required=True,
                description="Output sink for results"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "stream_id": {"type": "string"},
                "throughput": {"type": "number"},
                "latency_ms": {"type": "integer"},
                "metrics": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="a100"),
            HardwareRequirement(component="vram", min_value=16, recommended=40, unit="GB"),
            HardwareRequirement(component="network", min_value="10Gbps", recommended="100Gbps"),
            HardwareRequirement(component="ram", min_value=64, recommended=256, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=2, min_charge=2),
            PricingTier(name="per_million_events", model=PricingModel.PER_UNIT, unit_price=0.1, min_charge=1),
            PricingTier(name="high_throughput", model=PricingModel.PER_HOUR, unit_price=5, min_charge=5)
        ],
        capabilities=["streaming", "windowing", "aggregation", "cep"],
        tags=["streaming", "real-time", "analytics", "kafka", "flink"],
        max_concurrent=10,
        timeout_seconds=86400  # 24 hours
    ),
    
    "graph_analytics": ServiceDefinition(
        id="graph_analytics",
        name="Graph Analytics",
        category=ServiceCategory.DATA_ANALYTICS,
        description="Network analysis and graph algorithms on GPU",
        icon="🕸️",
        input_parameters=[
            ParameterDefinition(
                name="algorithm",
                type=ParameterType.ENUM,
                required=True,
                description="Graph algorithm",
                options=["pagerank", "community-detection", "shortest-path", "triangles", "clustering", "centrality"]
            ),
            ParameterDefinition(
                name="graph_data",
                type=ParameterType.FILE,
                required=True,
                description="Graph data file (edges list, adjacency matrix, etc.)"
            ),
            ParameterDefinition(
                name="graph_format",
                type=ParameterType.ENUM,
                required=False,
                description="Graph format",
                default="edges",
                options=["edges", "adjacency", "csr", "metis"]
            ),
            ParameterDefinition(
                name="parameters",
                type=ParameterType.OBJECT,
                required=False,
                description="Algorithm-specific parameters"
            ),
            ParameterDefinition(
                name="num_vertices",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of vertices",
                min_value=1
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "statistics": {"type": "object"},
                "graph_metrics": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3090"),
            HardwareRequirement(component="vram", min_value=8, recommended=24, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=64, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_million_edges", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1),
            PricingTier(name="large_graph", model=PricingModel.PER_UNIT, unit_price=0.005, min_charge=0.5)
        ],
        capabilities=["gpu-graph", "algorithms", "network-analysis", "fraud-detection"],
        tags=["graph", "network", "analytics", "pagerank", "fraud"],
        max_concurrent=5,
        timeout_seconds=3600
    ),
    
    "time_series_analysis": ServiceDefinition(
        id="time_series_analysis",
        name="Time Series Analysis",
        category=ServiceCategory.DATA_ANALYTICS,
        description="Analyze time series data with GPU-accelerated algorithms",
        icon="📈",
        input_parameters=[
            ParameterDefinition(
                name="analysis_type",
                type=ParameterType.ENUM,
                required=True,
                description="Analysis type",
                options=["forecasting", "anomaly-detection", "decomposition", "seasonality", "trend"]
            ),
            ParameterDefinition(
                name="time_series_data",
                type=ParameterType.FILE,
                required=True,
                description="Time series data file"
            ),
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Analysis model",
                options=["arima", "prophet", "lstm", "transformer", "holt-winters", "var"]
            ),
            ParameterDefinition(
                name="forecast_horizon",
                type=ParameterType.INTEGER,
                required=False,
                description="Forecast horizon",
                default=30,
                min_value=1,
                max_value=365
            ),
            ParameterDefinition(
                name="frequency",
                type=ParameterType.STRING,
                required=False,
                description="Data frequency (D, H, M, S)",
                default="D"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "forecast": {"type": "array"},
                "confidence_intervals": {"type": "array"},
                "model_metrics": {"type": "object"},
                "anomalies": {"type": "array"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_1k_points", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01),
            PricingTier(name="per_forecast", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.1),
            PricingTier(name="enterprise", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1)
        ],
        capabilities=["forecasting", "anomaly-detection", "decomposition", "seasonality"],
        tags=["time-series", "forecasting", "anomaly", "arima", "lstm"],
        max_concurrent=10,
        timeout_seconds=1800
    )
}
