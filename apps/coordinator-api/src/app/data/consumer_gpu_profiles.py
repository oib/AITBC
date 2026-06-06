"""Consumer GPU profiles data for edge GPU service"""

CONSUMER_GPU_PROFILES = {
    "gtx_1660": {
        "name": "NVIDIA GTX 1660",
        "architecture": "Turing",
        "memory_gb": 6,
        "compute_capability": "7.5",
        "power_watts": 120,
        "performance_score": 0.6,
        "supported_tasks": ["llm_inference", "image_generation", "video_processing"]
    },
    "rtx_3060": {
        "name": "NVIDIA RTX 3060",
        "architecture": "Ampere",
        "memory_gb": 12,
        "compute_capability": "8.6",
        "power_watts": 170,
        "performance_score": 0.8,
        "supported_tasks": ["llm_inference", "llm_training", "image_generation", "video_processing"]
    },
    "rtx_4090": {
        "name": "NVIDIA RTX 4090",
        "architecture": "Ada Lovelace",
        "memory_gb": 24,
        "compute_capability": "8.9",
        "power_watts": 450,
        "performance_score": 1.0,
        "supported_tasks": ["llm_inference", "llm_training", "image_generation", "video_processing", "scientific_computing"]
    }
}
