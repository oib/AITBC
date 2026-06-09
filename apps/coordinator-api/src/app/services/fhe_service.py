import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from aitbc import get_logger

logger = get_logger(__name__)


@dataclass
class FHEContext:
    """FHE encryption context"""

    scheme: str  # "bfv", "ckks", "concrete", "mock"
    poly_modulus_degree: int
    coeff_modulus: list
    scale: float
    public_key: bytes
    private_key: bytes | None = None
    provider_specific: dict[str, Any] | None = None


@dataclass
class EncryptedData:
    """Encrypted ML data"""

    ciphertext: bytes
    context: FHEContext
    shape: tuple
    dtype: str


class FHEProvider(ABC):
    """Abstract base class for FHE providers"""

    available: bool = False

    @abstractmethod
    def generate_context(self, scheme: str, **kwargs: Any) -> FHEContext:
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
    def encrypted_inference(self, model: dict[str, Any], encrypted_input: EncryptedData) -> EncryptedData:
        """Perform inference on encrypted data"""
        pass


class MockFHEProvider(FHEProvider):
    """Mock FHE provider for testing without real FHE libraries"""

    def __init__(self) -> None:
        self.available = True
        logger.info("Mock FHE provider initialized")

    def generate_context(self, scheme: str, **kwargs: Any) -> FHEContext:
        """Generate mock FHE context"""
        return FHEContext(
            scheme="mock",
            poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
            coeff_modulus=kwargs.get("coeff_modulus", [60, 40, 60]),
            scale=kwargs.get("scale", 2**40),
            public_key=b"mock_public_key",
            private_key=b"mock_private_key",
            provider_specific={"mock": True}
        )

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Mock encryption - serialize data as JSON (numpy-safe)."""
        import json
        # Convert numpy array to JSON-serializable list
        payload = {
            "data": data.tolist(),
            "shape": list(data.shape),
            "dtype": str(data.dtype)
        }
        ciphertext = json.dumps(payload).encode("utf-8")

        return EncryptedData(
            ciphertext=ciphertext,
            context=context,
            shape=data.shape,
            dtype=str(data.dtype)
        )

    def decrypt(self, encrypted_data: EncryptedData) -> np.ndarray:
        """Mock decryption - deserialize JSON back to numpy array."""
        import json
        payload = json.loads(encrypted_data.ciphertext.decode("utf-8"))
        return np.array(payload["data"], dtype=payload.get("dtype", "float64")).reshape(encrypted_data.shape)

    def encrypted_inference(self, model: dict[str, Any], encrypted_input: EncryptedData) -> EncryptedData:
        """Mock encrypted inference - perform computation on plaintext"""
        # Decrypt for mock computation
        plaintext_input = self.decrypt(encrypted_input)

        # Perform simple linear layer computation
        weights = model.get("weights")
        biases = model.get("biases")

        if weights is not None and biases is not None:
            if isinstance(weights, list):
                weights = np.array(weights)
            if isinstance(biases, list):
                biases = np.array(biases)

            # Simple matrix multiplication: y = Wx + b
            weights_array = weights.flatten()
            biases_array = biases.flatten()

            # Reshape input for matrix multiplication
            input_flat = plaintext_input.flatten()

            # Compute result
            result = np.dot(input_flat, weights_array) + biases_array[0]

            # Re-encrypt the result
            result_array = np.array([result])
            return self.encrypt(result_array, encrypted_input.context)
        else:
            raise ValueError("Model must contain weights and biases")


class TenSEALProvider(FHEProvider):
    """TenSEAL-based FHE provider for rapid prototyping"""

    def __init__(self) -> None:
        self.available = False
        self.ts: Any = None

        try:
            import tenseal as ts
            self.ts = ts
            self.available = True
            logger.info("TenSEAL provider initialized")
        except ImportError as e:
            logger.warning(f"TenSEAL not available: {e}")

    def generate_context(self, scheme: str, **kwargs: Any) -> FHEContext:
        """Generate TenSEAL context"""
        if not self.available:
            raise RuntimeError("TenSEAL provider is not available")
        assert self.ts is not None

        if scheme.lower() == "ckks":
            context = self.ts.context(
                self.ts.SCHEME_TYPE.CKKS,
                poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
                coeff_mod_bit_sizes=kwargs.get("coeff_mod_bit_sizes", [60, 40, 40, 60]),
            )
            context.global_scale = kwargs.get("scale", 2**40)
            context.generate_galois_keys()
        elif scheme.lower() == "bfv":
            context = self.ts.context(
                self.ts.SCHEME_TYPE.BFV,
                poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
                coeff_mod_bit_sizes=kwargs.get("coeff_mod_bit_sizes", [60, 40, 60]),
            )
        else:
            raise ValueError(f"Unsupported scheme: {scheme}")

        return FHEContext(
            scheme=scheme,
            poly_modulus_degree=kwargs.get("poly_modulus_degree", 8192),
            coeff_modulus=kwargs.get("coeff_mod_bit_sizes", [60, 40, 60]),
            scale=kwargs.get("scale", 2**40),
            public_key=context.serialize(save_secret_key=True),
            private_key=context.serialize(save_secret_key=True),
            provider_specific={"is_public": context.is_public}
        )

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Encrypt data using TenSEAL"""
        if not self.available:
            raise RuntimeError("TenSEAL provider is not available")
        assert self.ts is not None

        # Deserialize context
        ts_context = self.ts.context_from(context.public_key)

        # Encrypt data
        if context.scheme.lower() == "ckks":
            encrypted_tensor = self.ts.ckks_vector(ts_context, data.flatten())
        elif context.scheme.lower() == "bfv":
            encrypted_tensor = self.ts.bfv_vector(ts_context, data.flatten())
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
        if not self.available:
            raise RuntimeError("TenSEAL provider is not available")
        assert self.ts is not None

        # Deserialize context
        ts_context = self.ts.context_from(encrypted_data.context.public_key)

        # Deserialize ciphertext
        if encrypted_data.context.scheme.lower() == "ckks":
            encrypted_tensor = self.ts.ckks_vector_from(ts_context, encrypted_data.ciphertext)
        elif encrypted_data.context.scheme.lower() == "bfv":
            encrypted_tensor = self.ts.bfv_vector_from(ts_context, encrypted_data.ciphertext)
        else:
            raise ValueError(f"Unsupported scheme: {encrypted_data.context.scheme}")

        # Decrypt
        result = encrypted_tensor.decrypt()
        return np.array(result).reshape(encrypted_data.shape)

    def encrypted_inference(self, model: dict[str, Any], encrypted_input: EncryptedData) -> EncryptedData:
        """Perform basic encrypted inference"""
        if not self.available:
            raise RuntimeError("TenSEAL provider is not available")
        assert self.ts is not None

        # Deserialize context and input
        ts_context = self.ts.context_from(encrypted_input.context.public_key)
        encrypted_tensor = self.ts.ckks_vector_from(ts_context, encrypted_input.ciphertext)

        # Simple linear layer: y = Wx + b
        weights = model.get("weights")
        biases = model.get("biases")

        if weights is not None and biases is not None:
            # Convert weights and biases to numpy arrays if needed
            if isinstance(weights, list):
                weights = np.array(weights)
            if isinstance(biases, list):
                biases = np.array(biases)

            # Encrypt weights and biases
            weights_array = weights.flatten()
            biases_array = biases.flatten()

            encrypted_weights = self.ts.ckks_vector(ts_context, weights_array)
            encrypted_biases = self.ts.ckks_vector(ts_context, biases_array)

            # Perform encrypted matrix multiplication (simplified)
            # Note: Full matrix multiplication requires more complex FHE operations
            result = encrypted_tensor.dot(encrypted_weights)

            # Add bias - use plain addition since both are encrypted vectors
            # This will add element-wise, which is acceptable for our simplified use case
            result = result + encrypted_biases

            return EncryptedData(
                ciphertext=result.serialize(),
                context=encrypted_input.context,
                shape=(len(biases_array),),
                dtype="float32"
            )
        else:
            raise ValueError("Model must contain weights and biases")


class ConcreteMLProvider(FHEProvider):
    """Concrete ML provider for neural network inference"""

    def __init__(self) -> None:
        self.available = False
        self.cnp: Any = None

        # Concrete ML requires Python < 3.13
        if sys.version_info >= (3, 13):
            logger.warning(
                "Concrete ML requires Python <3.13. Current version: %s",
                sys.version.split()[0]
            )
        else:
            try:
                import concrete.numpy as cnp
                self.cnp = cnp
                self.available = True
            except ImportError as e:
                logger.warning(f"Concrete ML not available: {e}")

    def generate_context(self, scheme: str, **kwargs: Any) -> FHEContext:
        """Generate Concrete ML context"""
        if not self.available:
            raise RuntimeError("Concrete ML provider is not available")

        # Concrete ML uses compilation-based approach
        # Context is created during circuit compilation
        return FHEContext(
            scheme="concrete",
            poly_modulus_degree=kwargs.get("poly_modulus_degree", 1024),
            coeff_modulus=[kwargs.get("coeff_modulus", 15)],
            scale=1.0,
            public_key=b"concrete_context_placeholder",
            private_key=None,
            provider_specific={
                "p": kwargs.get("p", 15),
                "compilation_required": True
            }
        )

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        """Encrypt using Concrete ML"""
        if not self.available:
            raise RuntimeError("Concrete ML provider is not available")
        assert self.cnp is not None

        # Concrete ML encryption happens during circuit execution
        # For now, return a placeholder that can be used in circuit compilation
        p = context.provider_specific.get("p", 15) if context.provider_specific else 15

        # Convert data to appropriate format for Concrete ML
        encrypted_data = self.cnp.encrypt(data, p=p)

        return EncryptedData(
            ciphertext=str(encrypted_data).encode(),
            context=context,
            shape=data.shape,
            dtype=str(data.dtype)
        )

    def decrypt(self, encrypted_data: EncryptedData) -> np.ndarray:
        """Decrypt Concrete ML data"""
        if not self.available:
            raise RuntimeError("Concrete ML provider is not available")

        # Concrete ML decryption happens during circuit execution
        # This is a simplified placeholder
        logger.warning("Concrete ML decryption requires circuit execution context")
        return np.array([0.0])

    def encrypted_inference(self, model: dict[str, Any], encrypted_input: EncryptedData) -> EncryptedData:
        """Perform Concrete ML inference"""
        if not self.available:
            raise RuntimeError("Concrete ML provider is not available")

        # Concrete ML requires circuit compilation and execution
        # This is a simplified placeholder for the API interface
        logger.warning(
            "Concrete ML inference requires circuit compilation. "
            "Use the compile_and_execute method for full functionality."
        )

        return encrypted_input


class FHEService:
    """Main FHE service for AITBC"""

    def __init__(self) -> None:
        self.providers: dict[str, FHEProvider] = {}
        self.default_provider: str = "mock"

        # Mock provider (always available as fallback)
        self.providers["mock"] = MockFHEProvider()
        self.default_provider = "mock"
        logger.info("Mock FHE provider initialized as default")

        # TenSEAL provider (optional)
        tenseal_provider: FHEProvider = TenSEALProvider()
        if tenseal_provider.available:
            self.providers["tenseal"] = tenseal_provider
            logger.info("TenSEAL provider initialized")
        else:
            logger.info("TenSEAL provider not available")

        # Concrete ML provider (optional)
        concrete_provider: FHEProvider = ConcreteMLProvider()
        if concrete_provider.available:
            self.providers["concrete"] = concrete_provider
            logger.info("Concrete ML provider initialized")
        else:
            logger.info("Concrete ML provider not available (requires Python <3.13)")

        logger.info(f"Available FHE providers: {list(self.providers.keys())}")

    def get_provider(self, provider_name: str | None = None) -> FHEProvider:
        """Get FHE provider"""
        provider_name = provider_name or self.default_provider
        if provider_name not in self.providers:
            available = list(self.providers.keys())
            raise ValueError(
                f"Unknown FHE provider: {provider_name}. "
                f"Available providers: {available}"
            )
        return self.providers[provider_name]

    def generate_fhe_context(self, scheme: str = "ckks", provider: str | None = None, **kwargs: Any) -> FHEContext:
        """Generate FHE context"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.generate_context(scheme, **kwargs)

    def encrypt_ml_data(self, data: np.ndarray, context: FHEContext, provider: str | None = None) -> EncryptedData:
        """Encrypt ML data for FHE computation"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.encrypt(data, context)

    def decrypt_ml_data(self, encrypted_data: EncryptedData, provider: str | None = None) -> np.ndarray:
        """Decrypt FHE data"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.decrypt(encrypted_data)

    def encrypted_inference(
        self, model: dict[str, Any], encrypted_input: EncryptedData, provider: str | None = None
    ) -> EncryptedData:
        """Perform inference on encrypted data"""
        fhe_provider = self.get_provider(provider)
        return fhe_provider.encrypted_inference(model, encrypted_input)

    def list_providers(self) -> dict[str, bool]:
        """List available FHE providers"""
        return {name: provider.available for name, provider in self.providers.items()}
