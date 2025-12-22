"""
LLM inference plugin
"""

import asyncio
from typing import Dict, Any, List, Optional
import time

from .base import GPUPlugin, PluginResult
from .exceptions import PluginExecutionError


class LLMPlugin(GPUPlugin):
    """Plugin for Large Language Model inference"""
    
    def __init__(self):
        super().__init__()
        self.service_id = "llm_inference"
        self.name = "LLM Inference"
        self.version = "1.0.0"
        self.description = "Run inference on large language models"
        self.capabilities = ["generate", "stream", "chat"]
        self._model_cache = {}
    
    def setup(self) -> None:
        """Initialize LLM dependencies"""
        super().setup()
        
        # Check for transformers installation
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            self.transformers = AutoModelForCausalLM
            self.AutoTokenizer = AutoTokenizer
            self.pipeline = pipeline
        except ImportError:
            raise PluginExecutionError("Transformers not installed. Install with: pip install transformers accelerate")
        
        # Check for torch
        try:
            import torch
            self.torch = torch
        except ImportError:
            raise PluginExecutionError("PyTorch not installed. Install with: pip install torch")
    
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate LLM request parameters"""
        errors = []
        
        # Check required parameters
        if "prompt" not in request:
            errors.append("'prompt' is required")
        
        # Validate model
        model = request.get("model", "llama-7b")
        valid_models = [
            "llama-7b",
            "llama-13b", 
            "mistral-7b",
            "mixtral-8x7b",
            "gpt-3.5-turbo",
            "gpt-4"
        ]
        if model not in valid_models:
            errors.append(f"Invalid model. Must be one of: {', '.join(valid_models)}")
        
        # Validate max_tokens
        max_tokens = request.get("max_tokens", 256)
        if not isinstance(max_tokens, int) or max_tokens < 1 or max_tokens > 4096:
            errors.append("max_tokens must be an integer between 1 and 4096")
        
        # Validate temperature
        temperature = request.get("temperature", 0.7)
        if not isinstance(temperature, (int, float)) or temperature < 0.0 or temperature > 2.0:
            errors.append("temperature must be between 0.0 and 2.0")
        
        # Validate top_p
        top_p = request.get("top_p")
        if top_p is not None and (not isinstance(top_p, (int, float)) or top_p <= 0.0 or top_p > 1.0):
            errors.append("top_p must be between 0.0 and 1.0")
        
        return errors
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for LLM inference"""
        return {
            "gpu": "recommended",
            "vram_gb": 8,
            "ram_gb": 16,
            "cuda": "recommended"
        }
    
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute LLM inference"""
        start_time = time.time()
        
        try:
            # Validate request
            errors = self.validate_request(request)
            if errors:
                return PluginResult(
                    success=False,
                    error=f"Validation failed: {'; '.join(errors)}"
                )
            
            # Get parameters
            prompt = request["prompt"]
            model_name = request.get("model", "llama-7b")
            max_tokens = request.get("max_tokens", 256)
            temperature = request.get("temperature", 0.7)
            top_p = request.get("top_p", 0.9)
            do_sample = request.get("do_sample", True)
            stream = request.get("stream", False)
            
            # Load model and tokenizer
            model, tokenizer = await self._load_model(model_name)
            
            # Generate response
            loop = asyncio.get_event_loop()
            
            if stream:
                # Streaming generation
                generator = await loop.run_in_executor(
                    None,
                    lambda: self._generate_streaming(
                        model, tokenizer, prompt, max_tokens, temperature, top_p, do_sample
                    )
                )
                
                # Collect all tokens
                full_response = ""
                tokens = []
                for token in generator:
                    tokens.append(token)
                    full_response += token
                
                execution_time = time.time() - start_time
                
                return PluginResult(
                    success=True,
                    data={
                        "text": full_response,
                        "tokens": tokens,
                        "streamed": True
                    },
                    metrics={
                        "model": model_name,
                        "prompt_tokens": len(tokenizer.encode(prompt)),
                        "generated_tokens": len(tokens),
                        "tokens_per_second": len(tokens) / execution_time if execution_time > 0 else 0
                    },
                    execution_time=execution_time
                )
            else:
                # Regular generation
                response = await loop.run_in_executor(
                    None,
                    lambda: self._generate(
                        model, tokenizer, prompt, max_tokens, temperature, top_p, do_sample
                    )
                )
                
                execution_time = time.time() - start_time
                
                return PluginResult(
                    success=True,
                    data={
                        "text": response,
                        "streamed": False
                    },
                    metrics={
                        "model": model_name,
                        "prompt_tokens": len(tokenizer.encode(prompt)),
                        "generated_tokens": len(tokenizer.encode(response)) - len(tokenizer.encode(prompt)),
                        "tokens_per_second": (len(tokenizer.encode(response)) - len(tokenizer.encode(prompt))) / execution_time if execution_time > 0 else 0
                    },
                    execution_time=execution_time
                )
                
        except Exception as e:
            return PluginResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    async def _load_model(self, model_name: str):
        """Load LLM model and tokenizer with caching"""
        if model_name not in self._model_cache:
            loop = asyncio.get_event_loop()
            
            # Map model names to HuggingFace model IDs
            model_map = {
                "llama-7b": "meta-llama/Llama-2-7b-chat-hf",
                "llama-13b": "meta-llama/Llama-2-13b-chat-hf",
                "mistral-7b": "mistralai/Mistral-7B-Instruct-v0.1",
                "mixtral-8x7b": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "gpt-3.5-turbo": "openai-gpt",  # Would need OpenAI API
                "gpt-4": "openai-gpt-4"  # Would need OpenAI API
            }
            
            hf_model = model_map.get(model_name, model_name)
            
            # Load tokenizer
            tokenizer = await loop.run_in_executor(
                None,
                lambda: self.AutoTokenizer.from_pretrained(hf_model)
            )
            
            # Load model
            device = "cuda" if self.torch.cuda.is_available() else "cpu"
            model = await loop.run_in_executor(
                None,
                lambda: self.transformers.from_pretrained(
                    hf_model,
                    torch_dtype=self.torch.float16 if device == "cuda" else self.torch.float32,
                    device_map="auto" if device == "cuda" else None,
                    load_in_4bit=True if device == "cuda" and self.vram_gb < 16 else False
                )
            )
            
            self._model_cache[model_name] = (model, tokenizer)
        
        return self._model_cache[model_name]
    
    def _generate(
        self,
        model,
        tokenizer,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        do_sample: bool
    ) -> str:
        """Generate text without streaming"""
        inputs = tokenizer(prompt, return_tensors="pt")
        
        if self.torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        with self.torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=do_sample,
                pad_token_id=tokenizer.eos_token_id
            )
        
        # Decode only the new tokens
        new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(new_tokens, skip_special_tokens=True)
        
        return response
    
    def _generate_streaming(
        self,
        model,
        tokenizer,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        do_sample: bool
    ):
        """Generate text with streaming"""
        inputs = tokenizer(prompt, return_tensors="pt")
        
        if self.torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        # Simple streaming implementation
        # In production, you'd use model.generate with streamer
        with self.torch.no_grad():
            for i in range(max_tokens):
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=1,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=do_sample,
                    pad_token_id=tokenizer.eos_token_id
                )
                
                new_token = outputs[0][-1:]
                text = tokenizer.decode(new_token, skip_special_tokens=True)
                
                if text == tokenizer.eos_token:
                    break
                
                yield text
                
                # Update inputs for next iteration
                inputs["input_ids"] = self.torch.cat([inputs["input_ids"], new_token], dim=1)
                if "attention_mask" in inputs:
                    inputs["attention_mask"] = self.torch.cat([
                        inputs["attention_mask"], 
                        self.torch.ones((1, 1), device=inputs["attention_mask"].device)
                    ], dim=1)
    
    async def health_check(self) -> bool:
        """Check LLM health"""
        try:
            # Try to load a small model
            await self._load_model("mistral-7b")
            return True
        except Exception:
            return False
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        # Move models to CPU and clear cache
        for model, _ in self._model_cache.values():
            if hasattr(model, 'to'):
                model.to("cpu")
        self._model_cache.clear()
        
        # Clear GPU cache
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
