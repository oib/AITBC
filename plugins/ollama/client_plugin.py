#!/usr/bin/env python3
"""
AITBC Ollama Client Plugin - Submit LLM inference jobs to the network
"""

from typing import Any

import httpx


class OllamaClient:
    """Client for submitting Ollama jobs to AITBC network"""

    def __init__(self, coordinator_url: str, api_key: str):
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.client = httpx.Client()

    def list_available_models(self) -> list[str]:
        """Get available models from miners"""

        try:
            # For now, return common Ollama models
            # In production, this would query the network for available models
            return [
                "deepseek-r1:14b",
                "qwen2.5-coder:14b",
                "deepseek-coder-v2:latest",
                "gemma3:12b",
                "deepcoder:latest",
                "deepseek-coder:6.7b-base",
                "llama3.2:3b-instruct-q8_0",
                "mistral:latest",
                "llama3.2:latest",
                "gemma3:4b",
                "qwen2.5:1.5b",
                "gemma3:1b",
                "lauchacarro/qwen2.5-translator:latest"
            ]
        except Exception as e:
            print(f"Failed to get models: {e}")
            return []

    def submit_generation(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        ttl_seconds: int = 300
    ) -> str | None:
        """Submit a text generation job"""

        job_payload = {
            "type": "generate",
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if system_prompt:
            job_payload["system_prompt"] = system_prompt

        return self._submit_job(job_payload, ttl_seconds)

    def submit_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        ttl_seconds: int = 300
    ) -> str | None:
        """Submit a chat completion job"""

        job_payload = {
            "type": "chat",
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        return self._submit_job(job_payload, ttl_seconds)

    def submit_code_generation(
        self,
        model: str,
        prompt: str,
        language: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        ttl_seconds: int = 600
    ) -> str | None:
        """Submit a code generation job"""

        system_prompt = f"You are a helpful coding assistant. Generate {language or 'Python'} code."
        if language:
            system_prompt += f" Use {language} syntax."

        job_payload = {
            "type": "generate",
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        return self._submit_job(job_payload, ttl_seconds)

    def _submit_job(self, payload: dict[str, Any], ttl_seconds: int) -> str | None:
        """Submit job to coordinator"""

        job_data = {
            "payload": payload,
            "ttl_seconds": ttl_seconds
        }

        try:
            response = self.client.post(
                f"{self.coordinator_url}/v1/jobs",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key
                },
                json=job_data
            )

            if response.status_code == 201:
                job = response.json()
                return job['job_id']
            else:
                print(f"❌ Failed to submit job: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error submitting job: {e}")
            return None

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get job status and result"""

        try:
            response = self.client.get(
                f"{self.coordinator_url}/v1/jobs/{job_id}",
                headers={"X-Api-Key": self.api_key}
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get status: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error getting status: {e}")
            return None

    def wait_for_result(self, job_id: str, timeout: int = 60) -> dict[str, Any] | None:
        """Wait for job completion and return result"""

        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_job_status(job_id)

            if status:
                if status['state'] == 'completed':
                    return status
                elif status['state'] == 'failed':
                    print(f"❌ Job failed: {status.get('error', 'Unknown error')}")
                    return status
                elif status['state'] == 'expired':
                    print("⏰ Job expired")
                    return status

            time.sleep(2)

        print(f"⏰ Timeout waiting for job {job_id}")
        return None

# CLI interface
def main():
    import argparse

    parser = argparse.ArgumentParser(description="AITBC Ollama Client")
    parser.add_argument("--url", default="http://localhost:8001", help="Coordinator URL")
    parser.add_argument("--api-key", default="${CLIENT_API_KEY}", help="API key")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List models
    models_parser = subparsers.add_parser("models", help="List available models")

    # Generate text
    gen_parser = subparsers.add_parser("generate", help="Generate text")
    gen_parser.add_argument("model", help="Model name")
    gen_parser.add_argument("prompt", help="Text prompt")
    gen_parser.add_argument("--system", help="System prompt")
    gen_parser.add_argument("--temp", type=float, default=0.7, help="Temperature")
    gen_parser.add_argument("--max-tokens", type=int, help="Max tokens")

    # Chat
    chat_parser = subparsers.add_parser("chat", help="Chat completion")
    chat_parser.add_argument("model", help="Model name")
    chat_parser.add_argument("message", help="Message")
    chat_parser.add_argument("--temp", type=float, default=0.7, help="Temperature")

    # Code generation
    code_parser = subparsers.add_parser("code", help="Generate code")
    code_parser.add_argument("model", help="Model name")
    code_parser.add_argument("prompt", help="Code description")
    code_parser.add_argument("--lang", default="python", help="Programming language")

    # Check status
    status_parser = subparsers.add_parser("status", help="Check job status")
    status_parser.add_argument("job_id", help="Job ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    client = OllamaClient(args.url, args.api_key)

    if args.command == "models":
        models = client.list_available_models()
        print("🤖 Available Models:")
        for model in models:
            print(f"   • {model}")

    elif args.command == "generate":
        print(f"📝 Generating with {args.model}...")
        job_id = client.submit_generation(
            args.model,
            args.prompt,
            args.system,
            args.temp,
            args.max_tokens
        )

        if job_id:
            print(f"✅ Job submitted: {job_id}")
            result = client.wait_for_result(job_id)

            if result and result['state'] == 'completed':
                print("\n📄 Result:")
                print(result.get('result', {}).get('output', 'No output'))

    elif args.command == "chat":
        print(f"💬 Chatting with {args.model}...")
        messages = [{"role": "user", "content": args.message}]

        job_id = client.submit_chat(args.model, messages, args.temp)

        if job_id:
            print(f"✅ Job submitted: {job_id}")
            result = client.wait_for_result(job_id)

            if result and result['state'] == 'completed':
                print("\n🤖 Response:")
                print(result.get('result', {}).get('output', 'No response'))

    elif args.command == "code":
        print(f"💻 Generating {args.lang} code with {args.model}...")
        job_id = client.submit_code_generation(args.model, args.prompt, args.lang)

        if job_id:
            print(f"✅ Job submitted: {job_id}")
            result = client.wait_for_result(job_id)

            if result and result['state'] == 'completed':
                print("\n💾 Generated Code:")
                print(result.get('result', {}).get('output', 'No code'))

    elif args.command == "status":
        status = client.get_job_status(args.job_id)
        if status:
            print(f"📊 Job {args.job_id}:")
            print(f"   State: {status['state']}")
            print(f"   Miner: {status.get('assigned_miner_id', 'None')}")
            if status['state'] == 'completed':
                print(f"   Cost: {status.get('result', {}).get('cost', 0)} AITBC")

if __name__ == "__main__":
    main()
