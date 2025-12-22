"""
Scientific computing service definitions
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


SCIENTIFIC_COMPUTING_SERVICES = {
    "molecular_dynamics": ServiceDefinition(
        id="molecular_dynamics",
        name="Molecular Dynamics Simulation",
        category=ServiceCategory.SCIENTIFIC_COMPUTING,
        description="Run molecular dynamics simulations using GROMACS or NAMD",
        icon="🧬",
        input_parameters=[
            ParameterDefinition(
                name="software",
                type=ParameterType.ENUM,
                required=True,
                description="MD software package",
                options=["gromacs", "namd", "amber", "lammps", "desmond"]
            ),
            ParameterDefinition(
                name="structure_file",
                type=ParameterType.FILE,
                required=True,
                description="Molecular structure file (PDB, MOL2, etc)"
            ),
            ParameterDefinition(
                name="topology_file",
                type=ParameterType.FILE,
                required=False,
                description="Topology file"
            ),
            ParameterDefinition(
                name="force_field",
                type=ParameterType.ENUM,
                required=True,
                description="Force field to use",
                options=["AMBER", "CHARMM", "OPLS", "GROMOS", "DREIDING"]
            ),
            ParameterDefinition(
                name="simulation_time_ns",
                type=ParameterType.FLOAT,
                required=True,
                description="Simulation time in nanoseconds",
                min_value=0.1,
                max_value=1000
            ),
            ParameterDefinition(
                name="temperature_k",
                type=ParameterType.FLOAT,
                required=False,
                description="Temperature in Kelvin",
                default=300,
                min_value=0,
                max_value=500
            ),
            ParameterDefinition(
                name="pressure_bar",
                type=ParameterType.FLOAT,
                required=False,
                description="Pressure in bar",
                default=1,
                min_value=0,
                max_value=1000
            ),
            ParameterDefinition(
                name="time_step_fs",
                type=ParameterType.FLOAT,
                required=False,
                description="Time step in femtoseconds",
                default=2,
                min_value=0.5,
                max_value=5
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "trajectory_url": {"type": "string"},
                "log_url": {"type": "string"},
                "energy_data": {"type": "array"},
                "simulation_stats": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="a100"),
            HardwareRequirement(component="vram", min_value=16, recommended=40, unit="GB"),
            HardwareRequirement(component="cpu", min_value=16, recommended=64, unit="cores"),
            HardwareRequirement(component="ram", min_value=32, recommended=256, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=1000, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_ns", model=PricingModel.PER_UNIT, unit_price=0.1, min_charge=1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=2, min_charge=2),
            PricingTier(name="bulk_100ns", model=PricingModel.PER_UNIT, unit_price=0.05, min_charge=5)
        ],
        capabilities=["gpu-accelerated", "parallel", "ensemble", "free-energy"],
        tags=["molecular", "dynamics", "simulation", "biophysics", "chemistry"],
        max_concurrent=4,
        timeout_seconds=86400  # 24 hours
    ),
    
    "weather_modeling": ServiceDefinition(
        id="weather_modeling",
        name="Weather Modeling",
        category=ServiceCategory.SCIENTIFIC_COMPUTING,
        description="Run weather prediction and climate simulations",
        icon="🌦️",
        input_parameters=[
            ParameterDefinition(
                name="model",
                type=ParameterType.ENUM,
                required=True,
                description="Weather model",
                options=["WRF", "MM5", "IFS", "GFS", "ECMWF"]
            ),
            ParameterDefinition(
                name="region",
                type=ParameterType.OBJECT,
                required=True,
                description="Geographic region bounds",
                properties={
                    "lat_min": {"type": "number"},
                    "lat_max": {"type": "number"},
                    "lon_min": {"type": "number"},
                    "lon_max": {"type": "number"}
                }
            ),
            ParameterDefinition(
                name="forecast_hours",
                type=ParameterType.INTEGER,
                required=True,
                description="Forecast length in hours",
                min_value=1,
                max_value=384  # 16 days
            ),
            ParameterDefinition(
                name="resolution_km",
                type=ParameterType.FLOAT,
                required=False,
                description="Spatial resolution in kilometers",
                default=10,
                options=[1, 3, 5, 10, 25, 50]
            ),
            ParameterDefinition(
                name="output_variables",
                type=ParameterType.ARRAY,
                required=False,
                description="Variables to output",
                default=["temperature", "precipitation", "wind", "pressure"],
                items={"type": "string"}
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "forecast_data": {"type": "array"},
                "visualization_urls": {"type": "array"},
                "metadata": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="cpu", min_value=32, recommended=128, unit="cores"),
            HardwareRequirement(component="ram", min_value=64, recommended=512, unit="GB"),
            HardwareRequirement(component="storage", min_value=500, recommended=5000, unit="GB"),
            HardwareRequirement(component="network", min_value="10Gbps", recommended="100Gbps")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=5, min_charge=10),
            PricingTier(name="per_day", model=PricingModel.PER_UNIT, unit_price=100, min_charge=100),
            PricingTier(name="high_res", model=PricingModel.PER_HOUR, unit_price=10, min_charge=20)
        ],
        capabilities=["forecast", "climate", "ensemble", "data-assimilation"],
        tags=["weather", "climate", "forecast", "meteorology", "atmosphere"],
        max_concurrent=2,
        timeout_seconds=172800  # 48 hours
    ),
    
    "financial_modeling": ServiceDefinition(
        id="financial_modeling",
        name="Financial Modeling",
        category=ServiceCategory.SCIENTIFIC_COMPUTING,
        description="Run Monte Carlo simulations and risk analysis for financial models",
        icon="📊",
        input_parameters=[
            ParameterDefinition(
                name="model_type",
                type=ParameterType.ENUM,
                required=True,
                description="Financial model type",
                options=["monte-carlo", "option-pricing", "risk-var", "portfolio-optimization", "credit-risk"]
            ),
            ParameterDefinition(
                name="parameters",
                type=ParameterType.OBJECT,
                required=True,
                description="Model parameters"
            ),
            ParameterDefinition(
                name="num_simulations",
                type=ParameterType.INTEGER,
                required=True,
                description="Number of Monte Carlo simulations",
                default=10000,
                min_value=1000,
                max_value=10000000
            ),
            ParameterDefinition(
                name="time_steps",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of time steps",
                default=252,
                min_value=1,
                max_value=10000
            ),
            ParameterDefinition(
                name="confidence_levels",
                type=ParameterType.ARRAY,
                required=False,
                description="Confidence levels for VaR",
                default=[0.95, 0.99],
                items={"type": "number", "minimum": 0, "maximum": 1}
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "statistics": {"type": "object"},
                "risk_metrics": {"type": "object"},
                "confidence_intervals": {"type": "array"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3080"),
            HardwareRequirement(component="vram", min_value=8, recommended=16, unit="GB"),
            HardwareRequirement(component="cpu", min_value=8, recommended=32, unit="cores"),
            HardwareRequirement(component="ram", min_value=16, recommended=64, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_simulation", model=PricingModel.PER_UNIT, unit_price=0.00001, min_charge=0.1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1),
            PricingTier(name="enterprise", model=PricingModel.PER_UNIT, unit_price=0.000005, min_charge=0.5)
        ],
        capabilities=["monte-carlo", "var", "option-pricing", "portfolio", "risk-analysis"],
        tags=["finance", "risk", "monte-carlo", "var", "options"],
        max_concurrent=10,
        timeout_seconds=3600
    ),
    
    "physics_simulation": ServiceDefinition(
        id="physics_simulation",
        name="Physics Simulation",
        category=ServiceCategory.SCIENTIFIC_COMPUTING,
        description="Run particle physics and fluid dynamics simulations",
        icon="⚛️",
        input_parameters=[
            ParameterDefinition(
                name="simulation_type",
                type=ParameterType.ENUM,
                required=True,
                description="Physics simulation type",
                options=["particle-physics", "fluid-dynamics", "electromagnetics", "quantum", "astrophysics"]
            ),
            ParameterDefinition(
                name="solver",
                type=ParameterType.ENUM,
                required=True,
                description="Simulation solver",
                options=["geant4", "fluent", "comsol", "openfoam", "lammps", "gadget"]
            ),
            ParameterDefinition(
                name="geometry_file",
                type=ParameterType.FILE,
                required=False,
                description="Geometry or mesh file"
            ),
            ParameterDefinition(
                name="initial_conditions",
                type=ParameterType.OBJECT,
                required=True,
                description="Initial conditions and parameters"
            ),
            ParameterDefinition(
                name="simulation_time",
                type=ParameterType.FLOAT,
                required=True,
                description="Simulation time",
                min_value=0.001
            ),
            ParameterDefinition(
                name="particles",
                type=ParameterType.INTEGER,
                required=False,
                description="Number of particles",
                default=1000000,
                min_value=1000,
                max_value=100000000
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "results_url": {"type": "string"},
                "data_arrays": {"type": "object"},
                "visualizations": {"type": "array"},
                "statistics": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="a100"),
            HardwareRequirement(component="vram", min_value=16, recommended=40, unit="GB"),
            HardwareRequirement(component="cpu", min_value=16, recommended=64, unit="cores"),
            HardwareRequirement(component="ram", min_value=32, recommended=256, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=1000, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=2, min_charge=2),
            PricingTier(name="per_particle", model=PricingModel.PER_UNIT, unit_price=0.000001, min_charge=1),
            PricingTier(name="hpc", model=PricingModel.PER_HOUR, unit_price=5, min_charge=5)
        ],
        capabilities=["gpu-accelerated", "parallel", "mpi", "large-scale"],
        tags=["physics", "simulation", "particle", "fluid", "cfd"],
        max_concurrent=4,
        timeout_seconds=86400
    ),
    
    "bioinformatics": ServiceDefinition(
        id="bioinformatics",
        name="Bioinformatics Analysis",
        category=ServiceCategory.SCIENTIFIC_COMPUTING,
        description="DNA sequencing, protein folding, and genomic analysis",
        icon="🧬",
        input_parameters=[
            ParameterDefinition(
                name="analysis_type",
                type=ParameterType.ENUM,
                required=True,
                description="Bioinformatics analysis type",
                options=["dna-sequencing", "protein-folding", "alignment", "phylogeny", "variant-calling"]
            ),
            ParameterDefinition(
                name="sequence_file",
                type=ParameterType.FILE,
                required=True,
                description="Input sequence file (FASTA, FASTQ, BAM, etc)"
            ),
            ParameterDefinition(
                name="reference_file",
                type=ParameterType.FILE,
                required=False,
                description="Reference genome or protein structure"
            ),
            ParameterDefinition(
                name="algorithm",
                type=ParameterType.ENUM,
                required=True,
                description="Analysis algorithm",
                options=["blast", "bowtie", "bwa", "alphafold", "gatk", "clustal"]
            ),
            ParameterDefinition(
                name="parameters",
                type=ParameterType.OBJECT,
                required=False,
                description="Algorithm-specific parameters"
            )
        ],
        output_schema={
            "type": "object",
            "properties": {
                "results_file": {"type": "string"},
                "alignment_file": {"type": "string"},
                "annotations": {"type": "array"},
                "statistics": {"type": "object"}
            }
        },
        requirements=[
            HardwareRequirement(component="gpu", min_value="nvidia", recommended="rtx-3090"),
            HardwareRequirement(component="vram", min_value=8, recommended=24, unit="GB"),
            HardwareRequirement(component="cpu", min_value=16, recommended=32, unit="cores"),
            HardwareRequirement(component="ram", min_value=32, recommended=128, unit="GB"),
            HardwareRequirement(component="storage", min_value=100, recommended=500, unit="GB")
        ],
        pricing=[
            PricingTier(name="per_mb", model=PricingModel.PER_UNIT, unit_price=0.001, min_charge=0.1),
            PricingTier(name="per_hour", model=PricingModel.PER_HOUR, unit_price=1, min_charge=1),
            PricingTier(name="protein_folding", model=PricingModel.PER_UNIT, unit_price=0.01, min_charge=0.5)
        ],
        capabilities=["sequencing", "alignment", "folding", "annotation", "variant-calling"],
        tags=["bioinformatics", "genomics", "proteomics", "dna", "sequencing"],
        max_concurrent=5,
        timeout_seconds=7200
    )
}
