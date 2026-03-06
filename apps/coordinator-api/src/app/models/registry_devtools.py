"""
Development tools service definitions
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


DEVTOOLS_SERVICES = {
    "gpu_compilation": ServiceDefinition(
        id="gpu_compilation",
        name="GPU-Accelerated Compilation",
        category=ServiceCategory.DEVELOPMENT_TOOLS,
        description="Compile code with GPU acceleration (CUDA, HIP, OpenCL)",
        icon="⚙️",
        input_parameters=[
            ParameterDefinition(
                name="language",
                type=ParameterType.ENUM,
                required=True,
                description="Programming language",
                options=["cpp", "cuda", "hip", "opencl", "metal", "sycl"]
            ),
            ParameterDefinition(
                name="source_files",
                type=ParameterType.ARRAY,
                required=True,
                description="Source code files",
                items={"type": "string"}
            ),
            ParameterDefinition(
                name="build_type",
                type=ParameterType.ENUM,
                required=False,
                description="Build type",
                default="release",
                options=["debug", "release", "relwithdebinfo"]
            ),
            ParameterDefinition(
                name="target_arch",
                type=ParameterType.ENUM,
                required=False,
                description="Target architecture",
                default="sm_70",
                options=["sm_60", "sm_70", "sm_80", "sm_86", "sm_89", "sm_90"]
            ),
            ParameterDefinition(
                name="optimization_level",
                type=ParameterType.ENUM,
                required=False,
                description="Optimization level",
                default="O2",
                options=["O0", "O1", "O2", "O3", "Os"]
            ),
            ParameterDefinition(
                name="parallel_jobs",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of parallel compilation jobs",
                default=4,
                min_value=1,
                max_value=64
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "binary_url": {"type": "string"},
                "build_log": {"type": "string"},
                "compilation_time": {"type": "number"},
                "binary_size": {"type": "integer"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=4, recommended=8, unit="GB"),
            HardwareRequirement(component="cpu", min_value=8, recommended=16, unit="cores"),
            HardwareRequirement(component="ram", min_value=16, recommended=32, unit="GB"),
            HardwareRequirement(component="cuda", min_value="11.8")
        ],
        pricing=[
            PricingTier(name="per_minute", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_file", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01),
            PricingTier(name="enterprise", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1)
        ],
        capabilities=["cuda", "hip", "parallel-compilation", "incremental"],
        tags=["compilation", "cuda", "gpu", "cpp", "build"],
        max_concurrent=5,
        timeout_seconds=1800
    ),
    
    "model_training": ServiceDefinition(
        id="model_training",
        name="ML Model Training",
        category=ServiceCategory.DEVELOPMENT_TOOLS,
        description="Fine-tune or train machine learning models on client data",
        icon="🧠",
        input_parameters=[
            ParameterDefinition(
                name="model_type",
                type=ParameterType.ENUM,
                required=True,
                description="Model type",
                options=["transformer", "cnn", "rnn", "gan", "diffusion", "custom"]
            ),
            ParameterDefinition(
                name="base_model",
                type=ParameterType.STRING,
                required=False,
                description="Base model to fine-tune"
            ),
            ParameterDefinition(
                name="training_data",
                type=ParameterType.FILE,
                required=True,
                description="Training dataset"
            ),
            ParameterDefinition(
                name="validation_data",
                type=ParameterType.FILE,
                required=False,
                description="Validation dataset"
            ),
            ParameterDefinition(
                name="epochs",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of training epochs",
                default=10,
                min_value=1,
                max_value=1000
            ),
            ParameterDefinition(
                name="batch_size",
                type=ParameterType.INTEGER,
                required=False,
                description="Batch size",
                default=32,
                min_value=1,
                max_value=1024
            ),
            ParameterDefinition(
                name="learning_rate",
                type=ParameterType.FLOAT,
                required=False,
                description="Learning rate",
                default=0.001,
                min_value=0.00001,
                max_value=1
            ),
            ParameterDefinition(
                name="hyperparameters",
                type=ParameterType.OBJECT,
                required=False,
                description="Additional hyperparameters"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "model_url": {"type": "string"},
                "training_metrics": {"type": "object"},
                "loss_curves": {"type": "array"},
                "validation_scores": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="a100"),
            HardwareRequirement(component="vram", min_value=16, recommended=40, unit="GB"),
            HardwareRequirement(component="cpu", min_value=16, recommended=32, unit="cores"),
            HardwareRequirement(component="ram", min_value=32, recommended=128, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=1000, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_epoch", model=PricingModel.PER_UNIT, unit_price=0.1, min_charge=1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=2, min_charge=2),
            PricingTier(name="enterprise", model=PricingModel.PER_UNIT, unit_price=0.05, min_charge=0.5)
        ],
        capabilities=["fine-tuning", "training", "hyperparameter-tuning", "distributed"],
        tags=["ml", "training", "fine-tuning", "pytorch", "tensorflow"],
        max_concurrent=2,
        timeout_seconds=86400  # 24 hours
    ),
    
    "data_processing": ServiceDefinition(
        id="data_processing",
        name="Large Dataset Processing",
        category=ServiceCategory.DEVELOPMENT_TOOLS,
        description="Preprocess and transform large datasets",
        icon="📦",
        input_parameters=[
            ParameterDefinition(
                name="operation",
                type=ParameterType.ENUM,
                required=True,
                description="Processing operation",
                options=["clean", "transform", "normalize", "augment", "split", "encode"]
            ),
            ParameterDefinition(
                name="input_data",
                type=ParameterType.FILE,
                required=True,
                description="Input dataset"
            ),
            ParameterDefinition(
                name="output_format",
                type=ParameterType.ENUM,
                required=False,
                description="Output format",
                default="parquet",
                options=["csv", "json", "parquet", "hdf5", "feather", "pickle"]
            ),
            ParameterDefinition(
                name="chunk_size",
                type=ParameterType.INTEGER,
                required=False,
                description="Processing chunk size",
                default=10000,
                min_value=100,
                max_value=1000000
            ),
            ParameterDefinition(
                name="parameters",
                type=ParameterType.OBJECT,
                required=False,
                description="Operation-specific parameters"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "output_url": {"type": "string"},
                "processing_stats": {"type": "object"},
                "data_quality": {"type": "object"},
                "row_count": {"type": "integer"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="any", recommended="nvidia"),
            HardwareRequirement(component="vram", min_value=4, recommended=16, unit="GB"),
            HardwareRequirement(component="ram", min_value=16, recommended=64, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=1000, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_gb", model=PricingModel.PER_GB, unit_price=0.01, min_charge=0.1),
            PricingTier(name="per_million_rows", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.1),
            PricingTier(name="enterprise", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1)
        ],
        capabilities=["gpu-processing", "parallel", "streaming", "validation"],
        tags=["data", "preprocessing", "etl", "cleaning", "transformation"],
        max_concurrent=5,
        timeout_seconds=3600
    ),
    
    "simulation_testing": ServiceDefinition(
        id="simulation_testing",
        name="Hardware-in-the-Loop Testing",
        category=ServiceCategory.DEVELOPMENT_TOOLS,
        description="Run hardware simulations and testing workflows",
        icon="🔬",
        input_parameters=[
            ParameterDefinition(
                name="test_type",
                type=ParameterType.ENUM,
                required=True,
                description="Test type",
                options=["hardware", "firmware", "software", "integration", "performance"]
            ),
            ParameterDefinition(
                name="test_suite",
                type=ParameterType.FILE,
                required=True,
                description="Test suite configuration"
            ),
            ParameterDefinition(
                name="hardware_config",
                type=ParameterType.OBJECT,
                required=True,
                description="Hardware configuration"
            ),
            ParameterDefinition(
                name="duration",
                type=ParameterType.INTEGER,
                required=False,
                description="Test duration in hours",
                default=1,
                min_value=0.1,
                max_value=168  # 1 week
            ),
            ParameterDefinition(
                name="parallel_tests",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of parallel tests",
                default=1,
                min_value=1,
                max_value=10
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "test_results": {"type": "array"},
                "performance_metrics": {"type": "object"},
                "failure_logs": {"type": "array"},
                "coverage_report": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="any", recommended="nvidia"),
            HardwareRequirement(component="cpu", min_value=16, recommended=32, unit="cores"),
            HardwareRequirement(component="ram", min_value=32, recommended=128, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=500, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=2, min_charge=1),
            PricingTier(name="per_test", model=PricingModel.PER_UNIT, unit_price=0.1, min_charge=0.5),
            PricingTier(name="continuous", model=PricingModel.PER_HOUR, unit_price=5, min_charge=5)
        ],
        capabilities=["hardware-simulation", "automated-testing", "performance", "debugging"],
        tags=["testing", "simulation", "hardware", "hil", "verification"],
        max_concurrent=3,
        timeout_seconds=604800  # 1 week
    ),
    
    "code_generation": ServiceDefinition(
        id="code_generation",
        name="AI Code Generation",
        category=ServiceCategory.DEVELOPMENT_TOOLS,
        description="Generate code from natural language descriptions",
        icon="💻",
        input_parameters=[
            ParameterDefinition(
                name="language",
                type=ParameterType.ENUM,
                required=True,
                description="Target programming language",
                options=["python", "javascript", "cpp", "java", "go", "rust", "typescript", "sql"]
            ),
            ParameterDefinition(
                name="description",
                type=ParameterType.STRING,
                required=True,
                description="Natural language description of code to generate",
                max_value=2000
            ),
            ParameterDefinition(
                name="framework",
                type=ParameterType.STRING,
                required=False,
                description="Target framework or library"
            ),
            ParameterDefinition(
                name="code_style",
                type=ParameterType.ENUM,
                required=False,
                description="Code style preferences",
                default="standard",
                options=["standard", "functional", "oop", "minimalist"]
            ),
            ParameterDefinition(
                name="include_comments",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Include explanatory comments",
                default=True
            ),
            ParameterDefinition(
                name="include_tests",
                type=ParameterType.BOOLEAN,
                required=False,
                description="Generate unit tests",
                default=False
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "generated_code": {"type": "string"},
                "explanation": {"type": "string"},
                "usage_example": {"type": "string"},
                "test_code": {"type": "string"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="ram", min_value=8, recommended=16, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_generation", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.01),
            PricingTier(name="per_100_lines", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.01),
            PricingTier(name="with_tests", model=PricingModel.PER_UNIT, unit_price=0.02, min_charge=0.02)
        ],
        capabilities=["code-gen", "documentation", "test-gen", "refactoring"],
        tags=["code", "generation", "ai", "copilot", "automation"],
        max_concurrent=10,
        timeout_seconds=120
    )
}
