from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import numpy as np
from dataclasses import dataclass
from aitbc.logging import get_logger

@dataclass
class FHEContext:
    """FHE encryption context"""
    scheme: str  # "bfv", "ckks", "concrete"
    poly_modulus_degree: int
    coeff_modulus: List[int]
    scale: float
    public_key: bytes
    private_key: Optional[bytes] = None

@dataclass
class EncryptedData:
    """Encrypted ML data"""
    ciphertext: bytes
    context: FHEContext
    shape: Tuple[int, ...]
    dtype: str

class FHEProvider(ABC):
    """Abstract base class for FHE providers"""

    @abstractmethod
    def generate_context(self, scheme: str, **kwargs) -> FHEContext:
        """Generate FHE encryption context"""
        pass

    @abstractmethod
    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Encrypt data using FHE"""
        pass

    @abstractmethod
    def decrypt(self, encrypted_data: EncryptedData) -> np.ndarray:
        """Decrypt FHE data"""
        pass

    @abstractmethod
    def encrypted_inference(self,
                          model: Dict,
                          encrypted_input: EncryptedData) -> EncryptedData:
        """Perform inference on encrypted data"""
        pass

class TenSEALProvider(FHEProvider):
    """TenSEAL-based FHE provider for rapid prototyping"""

    def __init__(self):
        try:
            import tenseal as ts
            self.ts = ts
        except ImportError:
            raise ImportError("TenSEAL not installed. Install with: pip install tenseal")

    def generate_context(self, scheme: str, **kwargs) -> FHEContext:
        """Generate TenSEAL context"""
        if scheme.lower() == "ckks":
            context = self.ts.context(
                ts.SCHEME_TYPE.CKKS,
                poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
                coeff_mod_bit_sizes=kwargs.get("coeff_mod_bit_sizes", [60, 40, 40, 60])
            )
            context.global_scale = kwargs.get("scale", 2**40)
            context.generate_galois_keys()
        elif scheme.lower() == "bfv":
            context = self.ts.context(
                ts.SCHEME_TYPE.BFV,
                poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
                coeff_mod_bit_sizes=kwargs.get("coeff_mod_bit_sizes", [60, 40, 60])
            )
        else:
            raise ValueError(f"Unsupported scheme: {scheme}")

        return FHEContext(
            scheme=scheme,
            poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
            coeff_modulus=kwargs.get("coeff_mod_bit_sizes", [60, 40, 60]),
            scale=kwargs.get("scale", 2**40),
            public_key=context.serialize_pubkey(),
            private_key=context.serialize_seckey() if kwargs.get("generate_private_key") else None
        )

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Encrypt data using TenSEAL"""
        # Deserialize context
        ts_context = self.ts.context_from(context.public_key)

        # Encrypt data
        if context.scheme.lower() == "ckks":
            encrypted_tensor = self.ts.ckks_tensor(ts_context, data)
        elif context.scheme.lower() == "bfv":
            encrypted_tensor = self.ts.bfv_tensor(ts_context, data)
        else:
            raise ValueError(f"Unsupported scheme: {context.scheme}")

        return EncryptedData(
            ciphertext=encrypted_tensor.serialize(),
            context=context,
            shape=data.shape,
            dtype=str(data.dtype)
        )

    def decrypt(self, encrypted_data: EncryptedData) -> np.ndarray:
        """Decrypt TenSEAL data"""
        # Deserialize context
        ts_context = self.ts.context_from(encrypted_data.context.public_key)

        # Deserialize ciphertext
        if encrypted_data.context.scheme.lower() == "ckks":
            encrypted_tensor = self.ts.ckks_tensor_from(ts_context, encrypted_data.ciphertext)
        elif encrypted_data.context.scheme.lower() == "bfv":
            encrypted_tensor = self.ts.bfv_tensor_from(ts_context, encrypted_data.ciphertext)
        else:
            raise ValueError(f"Unsupported scheme: {encrypted_data.context.scheme}")

        # Decrypt
        result = encrypted_tensor.decrypt()
        return np.array(result).reshape(encrypted_data.shape)

    def encrypted_inference(self,
                          model: Dict,
                          encrypted_input: EncryptedData) -> EncryptedData:
        """Perform basic encrypted inference"""
        # This is a simplified example
        # Real implementation would depend on model type

        # Deserialize context and input
        ts_context = self.ts.context_from(encrypted_input.context.public_key)
        encrypted_tensor = self.ts.ckks_tensor_from(ts_context, encrypted_input.ciphertext)

        # Simple linear layer: y = Wx + b
        weights = model.get("weights")
        biases = model.get("biases")

        if weights is not None and biases is not None:
            # Encrypt weights and biases
            encrypted_weights = self.ts.ckks_tensor(ts_context, weights)
            encrypted_biases = self.ts.ckks_tensor(ts_context, biases)

            # Perform encrypted matrix multiplication
            result = encrypted_tensor.dot(encrypted_weights) + encrypted_biases

            return EncryptedData(
                ciphertext=result.serialize(),
                context=encrypted_input.context,
                shape=(len(biases),),
                dtype="float32"
            )
        else:
            raise ValueError("Model must contain weights and biases")

class ConcreteMLProvider(FHEProvider):
    """Concrete ML provider for neural network inference"""

    def __init__(self):
        try:
            import concrete.numpy as cnp
            self.cnp = cnp
        except ImportError:
            raise ImportError("Concrete ML not installed. Install with: pip install concrete-python")

    def generate_context(self, scheme: str, **kwargs) -> FHEContext:
        """Generate Concrete ML context"""
        # Concrete ML uses different context model
        return FHEContext(
            scheme="concrete",
            poly_modulus_degree=kwargs.get("poly_modulus_degree", 1024),
            coeff_modulus=[kwargs.get("coeff_modulus", 15)],
            scale=1.0,
            public_key=b"concrete_context",  # Simplified
            private_key=None
        )

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Encrypt using Concrete ML"""
        # Simplified Concrete ML encryption
        encrypted_circuit = self.cnp.encrypt(data, **{"p": 15})

        return EncryptedData(
            ciphertext=encrypted_circuit.serialize(),
            context=context,
            shape=data.shape,
            dtype=str(data.dtype)
        )

    def decrypt(self, encrypted_data: EncryptedData) -> np.ndarray:
        """Decrypt Concrete ML data"""
        # Simplified decryption
        return np.array([1, 2, 3])  # Placeholder

    def encrypted_inference(self,
                          model: Dict,
                          encrypted_input: EncryptedData) -> EncryptedData:
        """Perform Concrete ML inference"""
        # This would integrate with Concrete ML's neural network compilation
        return encrypted_input  # Placeholder

class FHEService:
    """Main FHE service for AITBC"""

    def __init__(self):
        providers = {"tenseal": TenSEALProvider()}

        # Optional Concrete ML provider
        try:
            providers["concrete"] = ConcreteMLProvider()
        except ImportError:
            logging.warning("Concrete ML not installed; skipping Concrete provider")

        self.providers = providers
        self.default_provider = "tenseal"

    def get_provider(self, provider_name: Optional[str] = None) -> FHEProvider:
        """Get FHE provider"""
        provider_name = provider_name or self.default_provider
        if provider_name not in self.providers:
            raise ValueError(f"Unknown FHE provider: {provider_name}")
        return self.providers[provider_name]

    def generate_fhe_context(self,
                           scheme: str = "ckks",
                           provider: Optional[str] = None,
                           **kwargs) -> FHEContext:
        """Generate FHE context"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.generate_context(scheme, **kwargs)

    def encrypt_ml_data(self,
                       data: np.ndarray,
                       context: FHEContext,
                       provider: Optional[str] = None) -> EncryptedData:
        """Encrypt ML data for FHE computation"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.encrypt(data, context)

    def encrypted_inference(self,
                          model: Dict,
                          encrypted_input: EncryptedData,
                          provider: Optional[str] = None) -> EncryptedData:
        """Perform inference on encrypted data"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.encrypted_inference(model, encrypted_input)
