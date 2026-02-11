# AITBC Ollama Plugin

Provides GPU-powered LLM inference services through Ollama, allowing miners to earn AITBC by processing AI/ML inference jobs.

## Features

- 🤖 **13 Available Models**: From lightweight 1B to large 14B models
- 💰 **Earn AITBC**: Get paid for GPU inference work
- 🚀 **Fast Processing**: Direct GPU acceleration via CUDA
- 💬 **Chat & Generation**: Support for both chat and text generation
- 💻 **Code Generation**: Specialized models for code generation

## Available Models

| Model | Size | Best For |
|-------|------|----------|
| deepseek-r1:14b | 9GB | General reasoning, complex tasks |
| qwen2.5-coder:14b | 9GB | Code generation, programming |
| deepseek-coder-v2:latest | 9GB | Advanced code generation |
| gemma3:12b | 8GB | General purpose, multilingual |
| deepcoder:latest | 9GB | Code completion, debugging |
| deepseek-coder:6.7b-base | 4GB | Lightweight code tasks |
| llama3.2:3b-instruct-q8_0 | 3GB | Fast inference, instruction following |
| mistral:latest | 4GB | Balanced performance |
| llama3.2:latest | 2GB | Quick responses, general use |
| gemma3:4b | 3GB | Efficient general tasks |
| qwen2.5:1.5b | 1GB | Fast, lightweight tasks |
| gemma3:1b | 815MB | Minimal resource usage |
| lauchacarro/qwen2.5-translator:latest | 1GB | Translation tasks |

## Quick Start

### 1. Start Ollama (if not running)
```bash
ollama serve
```

### 2. Start Mining
```bash
cd /home/oib/windsurf/aitbc/plugins/ollama
python3 miner_plugin.py
```

### 3. Submit Jobs (in another terminal)
```bash
# Text generation
python3 client_plugin.py generate llama3.2:latest "Explain quantum computing"

# Chat completion
python3 client_plugin.py chat mistral:latest "What is the meaning of life?"

# Code generation
python3 client_plugin.py code deepseek-coder-v2:latest "Create a REST API in Python" --lang python
```

## Pricing

Cost is calculated per 1M tokens:
- 14B models: ~0.12-0.14 AITBC
- 12B models: ~0.10 AITBC
- 6-9B models: ~0.06-0.08 AITBC
- 3-4B models: ~0.02-0.04 AITBC
- 1-2B models: ~0.01 AITBC

Miners earn 150% of the cost (50% markup).

## API Usage

### Submit Generation Job
```python
from client_plugin import OllamaClient

client = OllamaClient("http://localhost:8001", "${CLIENT_API_KEY}")

job_id = client.submit_generation(
    model="llama3.2:latest",
    prompt="Write a poem about AI",
    max_tokens=200
)

# Wait for result
result = client.wait_for_result(job_id)
print(result['result']['output'])
```

### Submit Chat Job
```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "How does blockchain work?"}
]

job_id = client.submit_chat("mistral:latest", messages)
```

### Submit Code Generation
```python
job_id = client.submit_code_generation(
    model="deepseek-coder-v2:latest",
    prompt="Create a function to sort a list in Python",
    language="python"
)
```

## Miner Configuration

The miner automatically:
- Registers all available Ollama models
- Sends heartbeats with GPU stats
- Processes jobs up to 2 concurrent tasks
- Calculates earnings based on token usage

## Testing

Run the test suite:
```bash
python3 test_ollama_plugin.py
```

## Integration with AITBC

The Ollama plugin integrates seamlessly with:
- **Coordinator**: Job distribution and management
- **Wallet**: Automatic earnings tracking
- **Explorer**: Job visibility as blocks
- **GPU Monitoring**: Real-time resource tracking

## Tips

1. **Choose the right model**: Smaller models for quick tasks, larger for complex reasoning
2. **Monitor earnings**: Check with `cd home/miner && python3 wallet.py balance`
3. **Batch jobs**: Submit multiple jobs for better utilization
4. **Temperature tuning**: Lower temp (0.3) for code, higher (0.8) for creative tasks

## Troubleshooting

- **Ollama not running**: Start with `ollama serve`
- **Model not found**: Pull with `ollama pull <model-name>`
- **Jobs timing out**: Increase TTL when submitting
- **Low earnings**: Use larger models for higher value jobs
