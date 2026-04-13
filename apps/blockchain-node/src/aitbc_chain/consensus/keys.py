"""
Validator Key Management
Handles cryptographic key operations for validators
"""

import os
import json
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

@dataclass
class ValidatorKeyPair:
    address: str
    private_key_pem: str
    public_key_pem: str
    created_at: float
    last_rotated: float

class KeyManager:
    """Manages validator cryptographic keys"""
    
    def __init__(self, keys_dir: str = "/opt/aitbc/dev"):
        self.keys_dir = keys_dir
        self.key_pairs: Dict[str, ValidatorKeyPair] = {}
        self._ensure_keys_directory()
        self._load_existing_keys()
    
    def _ensure_keys_directory(self):
        """Ensure keys directory exists and has proper permissions"""
        os.makedirs(self.keys_dir, mode=0o700, exist_ok=True)
    
    def _load_existing_keys(self):
        """Load existing key pairs from disk"""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        
        if os.path.exists(keys_file):
            try:
                with open(keys_file, 'r') as f:
                    keys_data = json.load(f)
                
                for address, key_data in keys_data.items():
                    self.key_pairs[address] = ValidatorKeyPair(
                        address=address,
                        private_key_pem=key_data['private_key_pem'],
                        public_key_pem=key_data['public_key_pem'],
                        created_at=key_data['created_at'],
                        last_rotated=key_data['last_rotated']
                    )
            except Exception as e:
                print(f"Error loading keys: {e}")
    
    def generate_key_pair(self, address: str) -> ValidatorKeyPair:
        """Generate new RSA key pair for validator"""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Serialize private key
        private_key_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        ).decode('utf-8')
        
        # Get public key
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Create key pair object
        current_time = time.time()
        key_pair = ValidatorKeyPair(
            address=address,
            private_key_pem=private_key_pem,
            public_key_pem=public_key_pem,
            created_at=current_time,
            last_rotated=current_time
        )
        
        # Store key pair
        self.key_pairs[address] = key_pair
        self._save_keys()
        
        return key_pair
    
    def get_key_pair(self, address: str) -> Optional[ValidatorKeyPair]:
        """Get key pair for validator"""
        return self.key_pairs.get(address)
    
    def rotate_key(self, address: str) -> Optional[ValidatorKeyPair]:
        """Rotate validator keys"""
        if address not in self.key_pairs:
            return None
        
        # Generate new key pair
        new_key_pair = self.generate_key_pair(address)
        
        # Update rotation time
        new_key_pair.created_at = self.key_pairs[address].created_at
        new_key_pair.last_rotated = time.time()
        
        self._save_keys()
        return new_key_pair
    
    def sign_message(self, address: str, message: str) -> Optional[str]:
        """Sign a message with validator's private key"""
        if address not in self.key_pairs:
            return None
        
        key_pair = self.key_pairs[address]
        
        # Load private key
        private_key = serialization.load_pem_private_key(
            key_pair.private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        
        # Sign message with explicit hash algorithm
        signature = private_key.sign(
            message.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature.hex()
    
    def verify_signature(self, address: str, message: str, signature: str) -> bool:
        """Verify a message signature"""
        if address not in self.key_pairs:
            return False
        
        key_pair = self.key_pairs[address]
        
        # Load public key
        public_key = serialization.load_pem_public_key(
            key_pair.public_key_pem.encode(),
            backend=default_backend()
        )
        
        try:
            # Convert hex signature to bytes
            signature_bytes = bytes.fromhex(signature)
            
            # Verify signature with explicit hash algorithm
            public_key.verify(
                signature_bytes,
                message.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        except Exception:
            return False
    
    def get_public_key_pem(self, address: str) -> Optional[str]:
        """Get public key PEM for validator"""
        key_pair = self.get_key_pair(address)
        return key_pair.public_key_pem if key_pair else None
    
    def _save_keys(self):
        """Save key pairs to disk"""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        
        keys_data = {}
        for address, key_pair in self.key_pairs.items():
            keys_data[address] = {
                'private_key_pem': key_pair.private_key_pem,
                'public_key_pem': key_pair.public_key_pem,
                'created_at': key_pair.created_at,
                'last_rotated': key_pair.last_rotated
            }
        
        try:
            with open(keys_file, 'w') as f:
                json.dump(keys_data, f, indent=2)
            
            # Set secure permissions
            os.chmod(keys_file, 0o600)
        except Exception as e:
            print(f"Error saving keys: {e}")
    
    def should_rotate_key(self, address: str, rotation_interval: int = 86400) -> bool:
        """Check if key should be rotated (default: 24 hours)"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return True
        
        return (time.time() - key_pair.last_rotated) >= rotation_interval
    
    def get_key_age(self, address: str) -> Optional[float]:
        """Get age of key in seconds"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return None
        
        return time.time() - key_pair.created_at

# Global key manager
key_manager = KeyManager()
