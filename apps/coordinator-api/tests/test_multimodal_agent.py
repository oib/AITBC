"""
Multi-Modal Agent Service Tests - Phase 5.1
Comprehensive test suite for multi-modal processing capabilities
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, create_engine
from sqlalchemy import StaticPool

from src.app.services.multimodal_agent import (
    MultiModalAgentService, ModalityType, ProcessingMode
)
from src.app.services.gpu_multimodal import GPUAcceleratedMultiModal
from src.app.services.modality_optimization import (
    ModalityOptimizationManager, OptimizationStrategy
)
from src.app.domain import AIAgentWorkflow, AgentExecution, AgentStatus


@pytest.fixture
def session():
    """Create test database session"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Create tables
    AIAgentWorkflow.metadata.create_all(engine)
    AgentExecution.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


@pytest.fixture
def sample_workflow(session: Session):
    """Create sample AI agent workflow"""
    workflow = AIAgentWorkflow(
        id=f"workflow_{uuid4().hex[:8]}",
        owner_id="test_user",
        name="Multi-Modal Test Workflow",
        description="Test workflow for multi-modal processing",
        steps={"step1": {"type": "multimodal", "modalities": ["text", "image"]}},
        dependencies={}
    )
    session.add(workflow)
    session.commit()
    return workflow


@pytest.fixture
def multimodal_service(session: Session):
    """Create multi-modal agent service"""
    return MultiModalAgentService(session)


@pytest.fixture
def gpu_service(session: Session):
    """Create GPU-accelerated multi-modal service"""
    return GPUAcceleratedMultiModal(session)


@pytest.fixture
def optimization_manager(session: Session):
    """Create modality optimization manager"""
    return ModalityOptimizationManager(session)


class TestMultiModalAgentService:
    """Test multi-modal agent service functionality"""
    
    @pytest.mark.asyncio
    async def test_process_text_only(self, multimodal_service: MultiModalAgentService):
        """Test processing text-only input"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text_input": "This is a test text for processing",
            "description": "Another text field"
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.SEQUENTIAL
        )
        
        assert result["agent_id"] == agent_id
        assert result["processing_mode"] == ProcessingMode.SEQUENTIAL
        assert ModalityType.TEXT in result["modalities_processed"]
        assert "text" in result["results"]
        assert result["results"]["text"]["modality"] == "text"
        assert result["results"]["text"]["processed_count"] == 2
        assert "performance_metrics" in result
        assert "processing_time_seconds" in result
    
    @pytest.mark.asyncio
    async def test_process_image_only(self, multimodal_service: MultiModalAgentService):
        """Test processing image-only input"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "image_data": {
                "pixels": [[0, 255, 128], [64, 192, 32]],
                "width": 2,
                "height": 2
            },
            "photo": {
                "image_data": "base64_encoded_image",
                "width": 224,
                "height": 224
            }
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.PARALLEL
        )
        
        assert result["agent_id"] == agent_id
        assert ModalityType.IMAGE in result["modalities_processed"]
        assert "image" in result["results"]
        assert result["results"]["image"]["modality"] == "image"
        assert result["results"]["image"]["processed_count"] == 2
    
    @pytest.mark.asyncio
    async def test_process_audio_only(self, multimodal_service: MultiModalAgentService):
        """Test processing audio-only input"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "audio_data": {
                "waveform": [0.1, 0.2, 0.3, 0.4],
                "sample_rate": 16000
            },
            "speech": {
                "audio_data": "encoded_audio",
                "spectrogram": [[1, 2, 3], [4, 5, 6]]
            }
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.FUSION
        )
        
        assert result["agent_id"] == agent_id
        assert ModalityType.AUDIO in result["modalities_processed"]
        assert "audio" in result["results"]
        assert result["results"]["audio"]["modality"] == "audio"
    
    @pytest.mark.asyncio
    async def test_process_video_only(self, multimodal_service: MultiModalAgentService):
        """Test processing video-only input"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "video_data": {
                "frames": [[[1, 2, 3], [4, 5, 6]]],
                "fps": 30,
                "duration": 1.0
            }
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.ATTENTION
        )
        
        assert result["agent_id"] == agent_id
        assert ModalityType.VIDEO in result["modalities_processed"]
        assert "video" in result["results"]
        assert result["results"]["video"]["modality"] == "video"
    
    @pytest.mark.asyncio
    async def test_process_multimodal_text_image(self, multimodal_service: MultiModalAgentService):
        """Test processing text and image modalities together"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text_description": "A beautiful sunset over mountains",
            "image_data": {
                "pixels": [[255, 200, 100], [150, 100, 50]],
                "width": 2,
                "height": 2
            }
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.FUSION
        )
        
        assert result["agent_id"] == agent_id
        assert ModalityType.TEXT in result["modalities_processed"]
        assert ModalityType.IMAGE in result["modalities_processed"]
        assert "text" in result["results"]
        assert "image" in result["results"]
        assert "fusion_result" in result["results"]
        assert "individual_results" in result["results"]["fusion_result"]
    
    @pytest.mark.asyncio
    async def test_process_all_modalities(self, multimodal_service: MultiModalAgentService):
        """Test processing all supported modalities"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text_input": "Sample text",
            "image_data": {"pixels": [[0, 255]], "width": 1, "height": 1},
            "audio_data": {"waveform": [0.1, 0.2], "sample_rate": 16000},
            "video_data": {"frames": [[[1, 2, 3]]], "fps": 30, "duration": 1.0},
            "tabular_data": [[1, 2, 3], [4, 5, 6]],
            "graph_data": {"nodes": [1, 2, 3], "edges": [(1, 2), (2, 3)]}
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.ATTENTION
        )
        
        assert len(result["modalities_processed"]) == 6
        assert all(modality.value in result["results"] for modality in result["modalities_processed"])
        assert "attention_weights" in result["results"]
        assert "attended_features" in result["results"]
    
    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_processing(self, multimodal_service: MultiModalAgentService):
        """Test difference between sequential and parallel processing"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text1": "First text",
            "text2": "Second text",
            "image1": {"pixels": [[0, 255]], "width": 1, "height": 1}
        }
        
        # Sequential processing
        sequential_result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.SEQUENTIAL
        )
        
        # Parallel processing
        parallel_result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.PARALLEL
        )
        
        # Both should produce valid results
        assert sequential_result["agent_id"] == agent_id
        assert parallel_result["agent_id"] == agent_id
        assert sequential_result["modalities_processed"] == parallel_result["modalities_processed"]
        
        # Processing times may differ
        assert "processing_time_seconds" in sequential_result
        assert "processing_time_seconds" in parallel_result
    
    @pytest.mark.asyncio
    async def test_empty_input_handling(self, multimodal_service: MultiModalAgentService):
        """Test handling of empty input"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {}
        
        with pytest.raises(ValueError, match="No valid modalities found"):
            await multimodal_service.process_multimodal_input(
                agent_id=agent_id,
                inputs=inputs,
                processing_mode=ProcessingMode.SEQUENTIAL
            )
    
    @pytest.mark.asyncio
    async def test_optimization_config(self, multimodal_service: MultiModalAgentService):
        """Test optimization configuration"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text_input": "Test text with optimization",
            "image_data": {"pixels": [[0, 255]], "width": 1, "height": 1}
        }
        
        optimization_config = {
            "fusion_weights": {"text": 0.7, "image": 0.3},
            "gpu_acceleration": True,
            "memory_limit_mb": 512
        }
        
        result = await multimodal_service.process_multimodal_input(
            agent_id=agent_id,
            inputs=inputs,
            processing_mode=ProcessingMode.FUSION,
            optimization_config=optimization_config
        )
        
        assert result["agent_id"] == agent_id
        assert "performance_metrics" in result
        # Optimization config should be reflected in results
        assert result["processing_mode"] == ProcessingMode.FUSION


class TestGPUAcceleratedMultiModal:
    """Test GPU-accelerated multi-modal processing"""
    
    @pytest.mark.asyncio
    async def test_gpu_attention_processing(self, gpu_service: GPUAcceleratedMultiModal):
        """Test GPU-accelerated attention processing"""
        
        # Create mock feature arrays
        modality_features = {
            "text": np.random.rand(100, 256),
            "image": np.random.rand(50, 512),
            "audio": np.random.rand(80, 128)
        }
        
        attention_config = {
            "attention_type": "scaled_dot_product",
            "num_heads": 8,
            "dropout_rate": 0.1
        }
        
        result = await gpu_service.accelerated_cross_modal_attention(
            modality_features=modality_features,
            attention_config=attention_config
        )
        
        assert "attended_features" in result
        assert "attention_matrices" in result
        assert "performance_metrics" in result
        assert "processing_time_seconds" in result
        assert result["acceleration_method"] in ["cuda_attention", "cpu_fallback"]
        
        # Check attention matrices
        attention_matrices = result["attention_matrices"]
        assert len(attention_matrices) > 0
        
        # Check performance metrics
        metrics = result["performance_metrics"]
        assert "speedup_factor" in metrics
        assert "gpu_utilization" in metrics
    
    @pytest.mark.asyncio
    async def test_cpu_fallback_attention(self, gpu_service: GPUAcceleratedMultiModal):
        """Test CPU fallback when GPU is not available"""
        
        # Mock GPU unavailability
        gpu_service._cuda_available = False
        
        modality_features = {
            "text": np.random.rand(50, 128),
            "image": np.random.rand(25, 256)
        }
        
        result = await gpu_service.accelerated_cross_modal_attention(
            modality_features=modality_features
        )
        
        assert result["acceleration_method"] == "cpu_fallback"
        assert result["gpu_utilization"] == 0.0
        assert "attended_features" in result
    
    @pytest.mark.asyncio
    async def test_multi_head_attention(self, gpu_service: GPUAcceleratedMultiModal):
        """Test multi-head attention configuration"""
        
        modality_features = {
            "text": np.random.rand(64, 512),
            "image": np.random.rand(32, 512)
        }
        
        attention_config = {
            "attention_type": "multi_head",
            "num_heads": 8,
            "dropout_rate": 0.1
        }
        
        result = await gpu_service.accelerated_cross_modal_attention(
            modality_features=modality_features,
            attention_config=attention_config
        )
        
        assert "attention_matrices" in result
        assert "performance_metrics" in result
        
        # Multi-head attention should produce different matrix structure
        matrices = result["attention_matrices"]
        for matrix_key, matrix in matrices.items():
            assert matrix.ndim >= 2  # Should be at least 2D


class TestModalityOptimization:
    """Test modality-specific optimization strategies"""
    
    @pytest.mark.asyncio
    async def test_text_optimization_speed(self, optimization_manager: ModalityOptimizationManager):
        """Test text optimization for speed"""
        
        text_data = ["This is a test sentence for optimization", "Another test sentence"]
        
        result = await optimization_manager.optimize_modality(
            modality=ModalityType.TEXT,
            data=text_data,
            strategy=OptimizationStrategy.SPEED
        )
        
        assert result["modality"] == "text"
        assert result["strategy"] == OptimizationStrategy.SPEED
        assert result["processed_count"] == 2
        assert "results" in result
        assert "optimization_metrics" in result
        
        # Check speed-focused optimization
        for text_result in result["results"]:
            assert text_result["optimization_method"] == "speed_focused"
            assert "tokens" in text_result
            assert "embeddings" in text_result
    
    @pytest.mark.asyncio
    async def test_text_optimization_memory(self, optimization_manager: ModalityOptimizationManager):
        """Test text optimization for memory"""
        
        text_data = "Long text that should be optimized for memory efficiency"
        
        result = await optimization_manager.optimize_modality(
            modality=ModalityType.TEXT,
            data=text_data,
            strategy=OptimizationStrategy.MEMORY
        )
        
        assert result["strategy"] == OptimizationStrategy.MEMORY
        
        for text_result in result["results"]:
            assert text_result["optimization_method"] == "memory_focused"
            assert "compression_ratio" in text_result["features"]
    
    @pytest.mark.asyncio
    async def test_text_optimization_accuracy(self, optimization_manager: ModalityOptimizationManager):
        """Test text optimization for accuracy"""
        
        text_data = "Text that should be processed with maximum accuracy"
        
        result = await optimization_manager.optimize_modality(
            modality=ModalityType.TEXT,
            data=text_data,
            strategy=OptimizationStrategy.ACCURACY
        )
        
        assert result["strategy"] == OptimizationStrategy.ACCURACY
        
        for text_result in result["results"]:
            assert text_result["optimization_method"] == "accuracy_focused"
            assert text_result["processing_quality"] == "maximum"
            assert "features" in text_result
    
    @pytest.mark.asyncio
    async def test_image_optimization_strategies(self, optimization_manager: ModalityOptimizationManager):
        """Test image optimization strategies"""
        
        image_data = {
            "width": 512,
            "height": 512,
            "channels": 3,
            "pixels": [[0, 255, 128] * 512] * 512  # Mock pixel data
        }
        
        # Test speed optimization
        speed_result = await optimization_manager.optimize_modality(
            modality=ModalityType.IMAGE,
            data=image_data,
            strategy=OptimizationStrategy.SPEED
        )
        
        assert speed_result["result"]["optimization_method"] == "speed_focused"
        assert speed_result["result"]["optimized_width"] < image_data["width"]
        assert speed_result["result"]["optimized_height"] < image_data["height"]
        
        # Test memory optimization
        memory_result = await optimization_manager.optimize_modality(
            modality=ModalityType.IMAGE,
            data=image_data,
            strategy=OptimizationStrategy.MEMORY
        )
        
        assert memory_result["result"]["optimization_method"] == "memory_focused"
        assert memory_result["result"]["optimized_channels"] == 1  # Grayscale
        
        # Test accuracy optimization
        accuracy_result = await optimization_manager.optimize_modality(
            modality=ModalityType.IMAGE,
            data=image_data,
            strategy=OptimizationStrategy.ACCURACY
        )
        
        assert accuracy_result["result"]["optimization_method"] == "accuracy_focused"
        assert accuracy_result["result"]["optimized_width"] >= image_data["width"]
    
    @pytest.mark.asyncio
    async def test_audio_optimization_strategies(self, optimization_manager: ModalityOptimizationManager):
        """Test audio optimization strategies"""
        
        audio_data = {
            "sample_rate": 44100,
            "duration": 5.0,
            "channels": 2,
            "waveform": [0.1 * i % 1.0 for i in range(220500)]  # 5 seconds of audio
        }
        
        # Test speed optimization
        speed_result = await optimization_manager.optimize_modality(
            modality=ModalityType.AUDIO,
            data=audio_data,
            strategy=OptimizationStrategy.SPEED
        )
        
        assert speed_result["result"]["optimization_method"] == "speed_focused"
        assert speed_result["result"]["optimized_sample_rate"] < audio_data["sample_rate"]
        assert speed_result["result"]["optimized_duration"] <= 2.0
        
        # Test memory optimization
        memory_result = await optimization_manager.optimize_modality(
            modality=ModalityType.AUDIO,
            data=audio_data,
            strategy=OptimizationStrategy.MEMORY
        )
        
        assert memory_result["result"]["optimization_method"] == "memory_focused"
        assert memory_result["result"]["optimized_sample_rate"] < speed_result["result"]["optimized_sample_rate"]
        assert memory_result["result"]["optimized_duration"] <= 1.0
    
    @pytest.mark.asyncio
    async def test_video_optimization_strategies(self, optimization_manager: ModalityOptimizationManager):
        """Test video optimization strategies"""
        
        video_data = {
            "fps": 30,
            "duration": 10.0,
            "width": 1920,
            "height": 1080
        }
        
        # Test speed optimization
        speed_result = await optimization_manager.optimize_modality(
            modality=ModalityType.VIDEO,
            data=video_data,
            strategy=OptimizationStrategy.SPEED
        )
        
        assert speed_result["result"]["optimization_method"] == "speed_focused"
        assert speed_result["result"]["optimized_fps"] < video_data["fps"]
        assert speed_result["result"]["optimized_width"] < video_data["width"]
        
        # Test memory optimization
        memory_result = await optimization_manager.optimize_modality(
            modality=ModalityType.VIDEO,
            data=video_data,
            strategy=OptimizationStrategy.MEMORY
        )
        
        assert memory_result["result"]["optimization_method"] == "memory_focused"
        assert memory_result["result"]["optimized_fps"] < speed_result["result"]["optimized_fps"]
        assert memory_result["result"]["optimized_width"] < speed_result["result"]["optimized_width"]
    
    @pytest.mark.asyncio
    async def test_multimodal_optimization(self, optimization_manager: ModalityOptimizationManager):
        """Test multi-modal optimization"""
        
        multimodal_data = {
            ModalityType.TEXT: ["Sample text for multimodal test"],
            ModalityType.IMAGE: {"width": 224, "height": 224, "channels": 3},
            ModalityType.AUDIO: {"sample_rate": 16000, "duration": 2.0, "channels": 1}
        }
        
        result = await optimization_manager.optimize_multimodal(
            multimodal_data=multimodal_data,
            strategy=OptimizationStrategy.BALANCED
        )
        
        assert result["multimodal_optimization"] is True
        assert result["strategy"] == OptimizationStrategy.BALANCED
        assert len(result["modalities_processed"]) == 3
        assert "text" in result["results"]
        assert "image" in result["results"]
        assert "audio" in result["results"]
        assert "aggregate_metrics" in result
        
        # Check aggregate metrics
        aggregate = result["aggregate_metrics"]
        assert "average_compression_ratio" in aggregate
        assert "total_processing_time" in aggregate
        assert "modalities_count" == 3


class TestPerformanceBenchmarks:
    """Test performance benchmarks for multi-modal operations"""
    
    @pytest.mark.asyncio
    async def benchmark_processing_modes(self, multimodal_service: MultiModalAgentService):
        """Benchmark different processing modes"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        inputs = {
            "text1": "Benchmark text 1",
            "text2": "Benchmark text 2",
            "image1": {"pixels": [[0, 255]], "width": 1, "height": 1},
            "image2": {"pixels": [[128, 128]], "width": 1, "height": 1}
        }
        
        modes = [ProcessingMode.SEQUENTIAL, ProcessingMode.PARALLEL, 
                ProcessingMode.FUSION, ProcessingMode.ATTENTION]
        
        results = {}
        for mode in modes:
            result = await multimodal_service.process_multimodal_input(
                agent_id=agent_id,
                inputs=inputs,
                processing_mode=mode
            )
            results[mode.value] = result["processing_time_seconds"]
        
        # Parallel should generally be faster than sequential
        assert results["parallel"] <= results["sequential"]
        
        # All modes should complete within reasonable time
        for mode, time_taken in results.items():
            assert time_taken < 10.0  # Should complete within 10 seconds
    
    @pytest.mark.asyncio
    async def benchmark_optimization_strategies(self, optimization_manager: ModalityOptimizationManager):
        """Benchmark different optimization strategies"""
        
        text_data = ["Benchmark text for optimization strategies"] * 100
        
        strategies = [OptimizationStrategy.SPEED, OptimizationStrategy.MEMORY,
                     OptimizationStrategy.ACCURACY, OptimizationStrategy.BALANCED]
        
        results = {}
        for strategy in strategies:
            result = await optimization_manager.optimize_modality(
                modality=ModalityType.TEXT,
                data=text_data,
                strategy=strategy
            )
            results[strategy.value] = {
                "time": result["processing_time_seconds"],
                "compression": result["optimization_metrics"]["compression_ratio"]
            }
        
        # Speed strategy should be fastest
        assert results["speed"]["time"] <= results["accuracy"]["time"]
        
        # Memory strategy should have best compression
        assert results["memory"]["compression"] >= results["speed"]["compression"]
    
    @pytest.mark.asyncio
    async def benchmark_scalability(self, multimodal_service: MultiModalAgentService):
        """Test scalability with increasing input sizes"""
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        
        # Test with different numbers of modalities
        test_cases = [
            {"text": "Single modality"},
            {"text": "Text", "image": {"pixels": [[0, 255]], "width": 1, "height": 1}},
            {"text": "Text", "image": {"pixels": [[0, 255]], "width": 1, "height": 1}, 
             "audio": {"waveform": [0.1, 0.2], "sample_rate": 16000}},
            {"text": "Text", "image": {"pixels": [[0, 255]], "width": 1, "height": 1},
             "audio": {"waveform": [0.1, 0.2], "sample_rate": 16000},
             "video": {"frames": [[[1, 2, 3]]], "fps": 30, "duration": 1.0}}
        ]
        
        processing_times = []
        for i, inputs in enumerate(test_cases):
            result = await multimodal_service.process_multimodal_input(
                agent_id=agent_id,
                inputs=inputs,
                processing_mode=ProcessingMode.PARALLEL
            )
            processing_times.append(result["processing_time_seconds"])
            
            # Processing time should increase reasonably
            if i > 0:
                # Should not increase exponentially
                assert processing_times[i] < processing_times[i-1] * 3
        
        # All should complete within reasonable time
        for time_taken in processing_times:
            assert time_taken < 15.0  # Should complete within 15 seconds


if __name__ == "__main__":
    pytest.main([__file__])
