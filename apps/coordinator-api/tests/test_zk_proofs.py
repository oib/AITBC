"""
Tests for ZK proof generation and verification
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from app.services.zk_proofs import ZKProofService
from app.models import JobReceipt, Job, JobResult
from app.domain import ReceiptPayload


class TestZKProofService:
    """Test cases for ZK proof service"""
    
    @pytest.fixture
    def zk_service(self):
        """Create ZK proof service instance"""
        with patch('app.services.zk_proofs.settings'):
            service = ZKProofService()
            return service
    
    @pytest.fixture
    def sample_job(self):
        """Create sample job for testing"""
        return Job(
            id="test-job-123",
            client_id="client-456",
            payload={"type": "test"},
            constraints={},
            requested_at=None,
            completed=True
        )
    
    @pytest.fixture
    def sample_job_result(self):
        """Create sample job result"""
        return {
            "result": "test-result",
            "result_hash": "0x1234567890abcdef",
            "units": 100,
            "unit_type": "gpu_seconds",
            "metrics": {"execution_time": 5.0}
        }
    
    @pytest.fixture
    def sample_receipt(self, sample_job):
        """Create sample receipt"""
        payload = ReceiptPayload(
            version="1.0",
            receipt_id="receipt-789",
            job_id=sample_job.id,
            provider="miner-001",
            client=sample_job.client_id,
            units=100,
            unit_type="gpu_seconds",
            price="0.1",
            started_at=1640995200,
            completed_at=1640995800,
            metadata={}
        )
        
        return JobReceipt(
            job_id=sample_job.id,
            receipt_id=payload.receipt_id,
            payload=payload.dict()
        )
    
    def test_service_initialization_with_files(self):
        """Test service initialization when circuit files exist"""
        with patch('app.services.zk_proofs.Path') as mock_path:
            # Mock file existence
            mock_path.return_value.exists.return_value = True
            
            service = ZKProofService()
            assert service.enabled is True
    
    def test_service_initialization_without_files(self):
        """Test service initialization when circuit files are missing"""
        with patch('app.services.zk_proofs.Path') as mock_path:
            # Mock file non-existence
            mock_path.return_value.exists.return_value = False
            
            service = ZKProofService()
            assert service.enabled is False
    
    @pytest.mark.asyncio
    async def test_generate_proof_basic_privacy(self, zk_service, sample_receipt, sample_job_result):
        """Test generating proof with basic privacy level"""
        if not zk_service.enabled:
            pytest.skip("ZK circuits not available")
        
        # Mock subprocess calls
        with patch('subprocess.run') as mock_run:
            # Mock successful proof generation
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({
                "proof": {"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]},
                "publicSignals": ["0x1234", "1000", "1640995800"]
            })
            
            # Generate proof
            proof = await zk_service.generate_receipt_proof(
                receipt=sample_receipt,
                job_result=sample_job_result,
                privacy_level="basic"
            )
            
            assert proof is not None
            assert "proof" in proof
            assert "public_signals" in proof
            assert proof["privacy_level"] == "basic"
            assert "circuit_hash" in proof
    
    @pytest.mark.asyncio
    async def test_generate_proof_enhanced_privacy(self, zk_service, sample_receipt, sample_job_result):
        """Test generating proof with enhanced privacy level"""
        if not zk_service.enabled:
            pytest.skip("ZK circuits not available")
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({
                "proof": {"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]},
                "publicSignals": ["1000", "1640995800"]
            })
            
            proof = await zk_service.generate_receipt_proof(
                receipt=sample_receipt,
                job_result=sample_job_result,
                privacy_level="enhanced"
            )
            
            assert proof is not None
            assert proof["privacy_level"] == "enhanced"
    
    @pytest.mark.asyncio
    async def test_generate_proof_service_disabled(self, zk_service, sample_receipt, sample_job_result):
        """Test proof generation when service is disabled"""
        zk_service.enabled = False
        
        proof = await zk_service.generate_receipt_proof(
            receipt=sample_receipt,
            job_result=sample_job_result,
            privacy_level="basic"
        )
        
        assert proof is None
    
    @pytest.mark.asyncio
    async def test_generate_proof_invalid_privacy_level(self, zk_service, sample_receipt, sample_job_result):
        """Test proof generation with invalid privacy level"""
        if not zk_service.enabled:
            pytest.skip("ZK circuits not available")
        
        with pytest.raises(ValueError, match="Unknown privacy level"):
            await zk_service.generate_receipt_proof(
                receipt=sample_receipt,
                job_result=sample_job_result,
                privacy_level="invalid"
            )
    
    @pytest.mark.asyncio
    async def test_verify_proof_success(self, zk_service):
        """Test successful proof verification"""
        if not zk_service.enabled:
            pytest.skip("ZK circuits not available")
        
        with patch('subprocess.run') as mock_run, \
             patch('builtins.open', mock_open(read_data='{"key": "value"}')):
            
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "true"
            
            result = await zk_service.verify_proof(
                proof={"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]},
                public_signals=["0x1234", "1000"]
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_verify_proof_failure(self, zk_service):
        """Test proof verification failure"""
        if not zk_service.enabled:
            pytest.skip("ZK circuits not available")
        
        with patch('subprocess.run') as mock_run, \
             patch('builtins.open', mock_open(read_data='{"key": "value"}')):
            
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Verification failed"
            
            result = await zk_service.verify_proof(
                proof={"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]},
                public_signals=["0x1234", "1000"]
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_verify_proof_service_disabled(self, zk_service):
        """Test proof verification when service is disabled"""
        zk_service.enabled = False
        
        result = await zk_service.verify_proof(
            proof={"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]},
            public_signals=["0x1234", "1000"]
        )
        
        assert result is False
    
    def test_hash_receipt(self, zk_service, sample_receipt):
        """Test receipt hashing"""
        receipt_hash = zk_service._hash_receipt(sample_receipt)
        
        assert isinstance(receipt_hash, str)
        assert len(receipt_hash) == 64  # SHA256 hex length
        assert all(c in '0123456789abcdef' for c in receipt_hash)
    
    def test_serialize_receipt(self, zk_service, sample_receipt):
        """Test receipt serialization for circuit"""
        serialized = zk_service._serialize_receipt(sample_receipt)
        
        assert isinstance(serialized, list)
        assert len(serialized) == 8
        assert all(isinstance(x, str) for x in serialized)


class TestZKProofIntegration:
    """Integration tests for ZK proof system"""
    
    @pytest.mark.asyncio
    async def test_receipt_creation_with_zk_proof(self):
        """Test receipt creation with ZK proof generation"""
        from app.services.receipts import ReceiptService
        from sqlmodel import Session
        
        # Create mock session
        session = Mock(spec=Session)
        
        # Create receipt service
        receipt_service = ReceiptService(session)
        
        # Create sample job
        job = Job(
            id="test-job-123",
            client_id="client-456",
            payload={"type": "test"},
            constraints={},
            requested_at=None,
            completed=True
        )
        
        # Mock ZK proof service
        with patch('app.services.receipts.zk_proof_service') as mock_zk:
            mock_zk.is_enabled.return_value = True
            mock_zk.generate_receipt_proof = AsyncMock(return_value={
                "proof": {"a": ["1", "2"]},
                "public_signals": ["0x1234"],
                "privacy_level": "basic"
            })
            
            # Create receipt with privacy
            receipt = await receipt_service.create_receipt(
                job=job,
                miner_id="miner-001",
                job_result={"result": "test"},
                result_metrics={"units": 100},
                privacy_level="basic"
            )
            
            assert receipt is not None
            assert "zk_proof" in receipt
            assert receipt["privacy_level"] == "basic"
    
    @pytest.mark.asyncio
    async def test_settlement_with_zk_proof(self):
        """Test cross-chain settlement with ZK proof"""
        from aitbc.settlement.hooks import SettlementHook
        from aitbc.settlement.manager import BridgeManager
        
        # Create mock bridge manager
        bridge_manager = Mock(spec=BridgeManager)
        
        # Create settlement hook
        settlement_hook = SettlementHook(bridge_manager)
        
        # Create sample job with ZK proof
        job = Job(
            id="test-job-123",
            client_id="client-456",
            payload={"type": "test"},
            constraints={},
            requested_at=None,
            completed=True,
            target_chain=2
        )
        
        # Create receipt with ZK proof
        receipt_payload = {
            "version": "1.0",
            "receipt_id": "receipt-789",
            "job_id": job.id,
            "provider": "miner-001",
            "client": job.client_id,
            "zk_proof": {
                "proof": {"a": ["1", "2"]},
                "public_signals": ["0x1234"]
            }
        }
        
        job.receipt = JobReceipt(
            job_id=job.id,
            receipt_id=receipt_payload["receipt_id"],
            payload=receipt_payload
        )
        
        # Test settlement message creation
        message = await settlement_hook._create_settlement_message(
            job,
            options={"use_zk_proof": True, "privacy_level": "basic"}
        )
        
        assert message.zk_proof is not None
        assert message.privacy_level == "basic"


# Helper function for mocking file operations
def mock_open(read_data=""):
    """Mock open function for file operations"""
    from unittest.mock import mock_open
    return mock_open(read_data=read_data)


# Benchmark tests
class TestZKProofPerformance:
    """Performance benchmarks for ZK proof operations"""
    
    @pytest.mark.asyncio
    async def test_proof_generation_time(self):
        """Benchmark proof generation time"""
        import time
        
        if not Path("apps/zk-circuits/receipt.wasm").exists():
            pytest.skip("ZK circuits not built")
        
        service = ZKProofService()
        if not service.enabled:
            pytest.skip("ZK service not enabled")
        
        # Create test data
        receipt = JobReceipt(
            job_id="benchmark-job",
            receipt_id="benchmark-receipt",
            payload={"test": "data"}
        )
        
        job_result = {"result": "benchmark"}
        
        # Measure proof generation time
        start_time = time.time()
        proof = await service.generate_receipt_proof(
            receipt=receipt,
            job_result=job_result,
            privacy_level="basic"
        )
        end_time = time.time()
        
        generation_time = end_time - start_time
        
        assert proof is not None
        assert generation_time < 30  # Should complete within 30 seconds
        
        print(f"Proof generation time: {generation_time:.2f} seconds")
    
    @pytest.mark.asyncio
    async def test_proof_verification_time(self):
        """Benchmark proof verification time"""
        import time
        
        service = ZKProofService()
        if not service.enabled:
            pytest.skip("ZK service not enabled")
        
        # Create test proof
        proof = {"a": ["1", "2"], "b": [["1", "2"], ["1", "2"]], "c": ["1", "2"]}
        public_signals = ["0x1234", "1000"]
        
        # Measure verification time
        start_time = time.time()
        result = await service.verify_proof(proof, public_signals)
        end_time = time.time()
        
        verification_time = end_time - start_time
        
        assert isinstance(result, bool)
        assert verification_time < 1  # Should complete within 1 second
        
        print(f"Proof verification time: {verification_time:.3f} seconds")
