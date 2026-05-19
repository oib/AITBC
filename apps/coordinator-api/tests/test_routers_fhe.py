"""
Tests for FHE router (Fully Homomorphic Encryption)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestFHERouter:
    """Test FHE router endpoints"""

    def test_fhe_health(self, client: TestClient):
        """Test FHE health endpoint"""
        response = client.get("/fhe/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "scheme" in data
        assert "available" in data

    def test_generate_keys(self, client: TestClient):
        """Test generating FHE keys"""
        response = client.post("/fhe/keys/generate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "public_key" in data
        assert "secret_key" in data
        assert "key_id" in data

    def test_encrypt(self, client: TestClient):
        """Test encrypting data"""
        # First generate keys
        keys_response = client.post("/fhe/keys/generate")
        public_key = keys_response.json()["public_key"]
        
        encrypt_data = {
            "public_key": public_key,
            "plaintext": [1, 2, 3, 4, 5],
            "scheme": "BFV"
        }
        
        response = client.post("/fhe/encrypt", json=encrypt_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "ciphertext" in data
        assert "encryption_id" in data

    def test_encrypt_batch(self, client: TestClient):
        """Test batch encryption"""
        keys_response = client.post("/fhe/keys/generate")
        public_key = keys_response.json()["public_key"]
        
        batch_data = {
            "public_key": public_key,
            "plaintexts": [[1, 2], [3, 4], [5, 6]]
        }
        
        response = client.post("/fhe/encrypt/batch", json=batch_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "ciphertexts" in data
        assert len(data["ciphertexts"]) == 3

    def test_decrypt(self, client: TestClient):
        """Test decrypting data"""
        # Generate keys
        keys_response = client.post("/fhe/keys/generate")
        public_key = keys_response.json()["public_key"]
        secret_key = keys_response.json()["secret_key"]
        
        # Encrypt
        encrypt_response = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [42, 100],
            "scheme": "BFV"
        })
        ciphertext = encrypt_response.json()["ciphertext"]
        
        # Decrypt
        decrypt_data = {
            "secret_key": secret_key,
            "ciphertext": ciphertext
        }
        
        response = client.post("/fhe/decrypt", json=decrypt_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "plaintext" in data
        assert data["plaintext"] == [42, 100]

    def test_add_encrypted(self, client: TestClient):
        """Test homomorphic addition"""
        keys_response = client.post("/fhe/keys/generate")
        public_key = keys_response.json()["public_key"]
        
        # Encrypt two values
        ct1 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [10],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        ct2 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [20],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        # Add them
        add_data = {
            "ciphertext_a": ct1,
            "ciphertext_b": ct2,
            "public_key": public_key
        }
        
        response = client.post("/fhe/operations/add", json=add_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result_ciphertext" in data

    def test_multiply_encrypted(self, client: TestClient):
        """Test homomorphic multiplication"""
        keys_response = client.post("/fhe/keys/generate")
        public_key = keys_response.json()["public_key"]
        
        ct1 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [5],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        ct2 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [7],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        multiply_data = {
            "ciphertext_a": ct1,
            "ciphertext_b": ct2,
            "public_key": public_key
        }
        
        response = client.post("/fhe/operations/multiply", json=multiply_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_fhe_info(self, client: TestClient):
        """Test FHE info endpoint"""
        response = client.get("/fhe/info")
        assert response.status_code == 200
        data = response.json()
        assert "scheme" in data
        assert "supported_operations" in data
        assert "security_level" in data


@pytest.mark.integration
class TestFHEIntegration:
    """Integration tests for FHE workflow"""

    def test_full_fhe_workflow(self, client: TestClient):
        """Test complete encrypt-compute-decrypt workflow"""
        # 1. Generate keys
        keys = client.post("/fhe/keys/generate").json()
        public_key = keys["public_key"]
        secret_key = keys["secret_key"]
        
        # 2. Encrypt two numbers
        ct1 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [15],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        ct2 = client.post("/fhe/encrypt", json={
            "public_key": public_key,
            "plaintext": [25],
            "scheme": "BFV"
        }).json()["ciphertext"]
        
        # 3. Add them homomorphically
        sum_ct = client.post("/fhe/operations/add", json={
            "ciphertext_a": ct1,
            "ciphertext_b": ct2,
            "public_key": public_key
        }).json()["result_ciphertext"]
        
        # 4. Decrypt result
        result = client.post("/fhe/decrypt", json={
            "secret_key": secret_key,
            "ciphertext": sum_ct
        }).json()
        
        # 5. Verify: 15 + 25 = 40
        assert result["plaintext"] == [40]
