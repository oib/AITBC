#!/usr/bin/env python3
"""
AITBC Ollama Plugin Service - Provides GPU-powered LLM inference via Ollama
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaPlugin:
    """Ollama plugin for AITBC - provides LLM inference services"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.client = httpx.AsyncClient(timeout=60.0)
        self.models_cache = None
        self.last_cache_update = None
        
    async def get_models(self) -> list:
        """Get available models from Ollama"""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
            return []
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
    
    async def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate text using Ollama model"""
        
        request_data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        if system_prompt:
            request_data["system"] = system_prompt
            
        if max_tokens:
            request_data["options"]["num_predict"] = max_tokens
        
        try:
            logger.info(f"Generating with model: {model}")
            start_time = datetime.now()
            
            response = await self.client.post(
                f"{self.ollama_url}/api/generate",
                json=request_data
            )
            
            if response.status_code == 200:
                result = response.json()
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                return {
                    "success": True,
                    "text": result.get("response", ""),
                    "model": model,
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                    "duration_seconds": duration,
                    "done": result.get("done", False)
                }
            else:
                return {
                    "success": False,
                    "error": f"Ollama error: {response.status_code}",
                    "details": response.text
                }
                
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def chat(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Chat with Ollama model"""
        
        request_data = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        if max_tokens:
            request_data["options"]["num_predict"] = max_tokens
        
        try:
            logger.info(f"Chat with model: {model}")
            start_time = datetime.now()
            
            response = await self.client.post(
                f"{self.ollama_url}/api/chat",
                json=request_data
            )
            
            if response.status_code == 200:
                result = response.json()
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                return {
                    "success": True,
                    "message": result.get("message", {}),
                    "model": model,
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                    "duration_seconds": duration,
                    "done": result.get("done", False)
                }
            else:
                return {
                    "success": False,
                    "error": f"Ollama error: {response.status_code}",
                    "details": response.text
                }
                
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_model_info(self, model: str) -> Dict[str, Any]:
        """Get detailed information about a model"""
        try:
            response = await self.client.post(
                f"{self.ollama_url}/api/show",
                json={"name": model}
            )
            
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.error(f"Failed to get model info: {e}")
            return {}
    
    def calculate_cost(self, model: str, tokens: int) -> float:
        """Calculate cost for inference based on model and tokens"""
        # Pricing per 1M tokens (adjust based on your pricing model)
        pricing = {
            "deepseek-r1:14b": 0.14,
            "qwen2.5-coder:14b": 0.12,
            "deepseek-coder-v2:latest": 0.12,
            "gemma3:12b": 0.10,
            "deepcoder:latest": 0.08,
            "deepseek-coder:6.7b-base": 0.06,
            "llama3.2:3b-instruct-q8_0": 0.04,
            "mistral:latest": 0.04,
            "llama3.2:latest": 0.02,
            "gemma3:4b": 0.02,
            "qwen2.5:1.5b": 0.01,
            "gemma3:1b": 0.01,
            "lauchacarro/qwen2.5-translator:latest": 0.01
        }
        
        price_per_million = pricing.get(model, 0.05)  # Default price
        cost = (tokens / 1_000_000) * price_per_million
        return round(cost, 6)

# Service instance
ollama_service = OllamaPlugin()

# AITBC Plugin Interface
async def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle AITBC plugin requests"""
    
    action = request.get("action")
    
    if action == "list_models":
        models = await ollama_service.get_models()
        return {
            "success": True,
            "models": [{"name": m["name"], "size": m["size"]} for m in models]
        }
    
    elif action == "generate":
        result = await ollama_service.generate(
            model=request.get("model"),
            prompt=request.get("prompt"),
            system_prompt=request.get("system_prompt"),
            temperature=request.get("temperature", 0.7),
            max_tokens=request.get("max_tokens")
        )
        
        if result["success"]:
            # Add cost calculation
            result["cost"] = ollama_service.calculate_cost(
                result["model"],
                result["total_tokens"]
            )
        
        return result
    
    elif action == "chat":
        result = await ollama_service.chat(
            model=request.get("model"),
            messages=request.get("messages"),
            temperature=request.get("temperature", 0.7),
            max_tokens=request.get("max_tokens")
        )
        
        if result["success"]:
            # Add cost calculation
            result["cost"] = ollama_service.calculate_cost(
                result["model"],
                result["total_tokens"]
            )
        
        return result
    
    elif action == "model_info":
        model = request.get("model")
        info = await ollama_service.get_model_info(model)
        return {
            "success": True,
            "info": info
        }
    
    else:
        return {
            "success": False,
            "error": f"Unknown action: {action}"
        }

if __name__ == "__main__":
    # Test the service
    async def test():
        # List models
        models = await ollama_service.get_models()
        print(f"Available models: {len(models)}")
        
        # Test generation
        if models:
            result = await ollama_service.generate(
                model=models[0]["name"],
                prompt="What is AITBC?",
                max_tokens=100
            )
            print(f"Generation result: {result}")
    
    asyncio.run(test())
