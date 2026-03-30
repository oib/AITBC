"""Multi-modal processing commands for AITBC CLI"""

import click
import httpx
import json
import base64
import mimetypes
from typing import Optional, Dict, Any, List
from pathlib import Path
from ..utils import output, error, success, warning


@click.group()
def multimodal():
    """Multi-modal agent processing and cross-modal operations"""
    pass


@multimodal.command()
@click.option("--name", required=True, help="Multi-modal agent name")
@click.option("--modalities", required=True, help="Comma-separated modalities (text,image,audio,video)")
@click.option("--description", default="", help="Agent description")
@click.option("--model-config", type=click.File('r'), help="Model configuration JSON file")
@click.option("--gpu-acceleration", is_flag=True, help="Enable GPU acceleration")
@click.pass_context
def agent(ctx, name: str, modalities: str, description: str, model_config, gpu_acceleration: bool):
    """Create multi-modal agent"""
    config = ctx.obj['config']
    
    modality_list = [mod.strip() for mod in modalities.split(',')]
    
    agent_data = {
        "name": name,
        "description": description,
        "modalities": modality_list,
        "gpu_acceleration": gpu_acceleration,
        "agent_type": "multimodal"
    }
    
    if model_config:
        try:
            config_data = json.load(model_config)
            agent_data["model_config"] = config_data
        except Exception as e:
            error(f"Failed to read model config file: {e}")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents",
                headers={"X-Api-Key": config.api_key or ""},
                json=agent_data
            )
            
            if response.status_code == 201:
                agent = response.json()
                success(f"Multi-modal agent created: {agent['id']}")
                output(agent, ctx.obj['output_format'])
            else:
                error(f"Failed to create multi-modal agent: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@multimodal.command()
@click.argument("agent_id")
@click.option("--text", help="Text input")
@click.option("--image", type=click.Path(exists=True), help="Image file path")
@click.option("--audio", type=click.Path(exists=True), help="Audio file path")
@click.option("--video", type=click.Path(exists=True), help="Video file path")
@click.option("--output-format", default="json", type=click.Choice(["json", "text", "binary"]),
              help="Output format for results")
@click.pass_context
def process(ctx, agent_id: str, text: Optional[str], image: Optional[str], 
           audio: Optional[str], video: Optional[str], output_format: str):
    """Process multi-modal inputs with agent"""
    config = ctx.obj['config']
    
    # Prepare multi-modal data
    modal_data = {}
    
    if text:
        modal_data["text"] = text
    
    if image:
        try:
            with open(image, 'rb') as f:
                image_data = f.read()
            modal_data["image"] = {
                "data": base64.b64encode(image_data).decode(),
                "mime_type": mimetypes.guess_type(image)[0] or "image/jpeg",
                "filename": Path(image).name
            }
        except Exception as e:
            error(f"Failed to read image file: {e}")
            return
    
    if audio:
        try:
            with open(audio, 'rb') as f:
                audio_data = f.read()
            modal_data["audio"] = {
                "data": base64.b64encode(audio_data).decode(),
                "mime_type": mimetypes.guess_type(audio)[0] or "audio/wav",
                "filename": Path(audio).name
            }
        except Exception as e:
            error(f"Failed to read audio file: {e}")
            return
    
    if video:
        try:
            with open(video, 'rb') as f:
                video_data = f.read()
            modal_data["video"] = {
                "data": base64.b64encode(video_data).decode(),
                "mime_type": mimetypes.guess_type(video)[0] or "video/mp4",
                "filename": Path(video).name
            }
        except Exception as e:
            error(f"Failed to read video file: {e}")
            return
    
    if not modal_data:
        error("At least one modality input must be provided")
        return
    
    process_data = {
        "modalities": modal_data,
        "output_format": output_format
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/process",
                headers={"X-Api-Key": config.api_key or ""},
                json=process_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success("Multi-modal processing completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to process multi-modal inputs: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@multimodal.command()
@click.argument("agent_id")
@click.option("--dataset", default="coco_vqa", help="Dataset name for benchmarking")
@click.option("--metrics", default="accuracy,latency", help="Comma-separated metrics to evaluate")
@click.option("--iterations", default=100, help="Number of benchmark iterations")
@click.pass_context
def benchmark(ctx, agent_id: str, dataset: str, metrics: str, iterations: int):
    """Benchmark multi-modal agent performance"""
    config = ctx.obj['config']
    
    benchmark_data = {
        "dataset": dataset,
        "metrics": [m.strip() for m in metrics.split(',')],
        "iterations": iterations
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/benchmark",
                headers={"X-Api-Key": config.api_key or ""},
                json=benchmark_data
            )
            
            if response.status_code == 202:
                benchmark = response.json()
                success(f"Benchmark started: {benchmark['id']}")
                output(benchmark, ctx.obj['output_format'])
            else:
                error(f"Failed to start benchmark: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@multimodal.command()
@click.argument("agent_id")
@click.option("--objective", default="throughput", 
              type=click.Choice(["throughput", "latency", "accuracy", "efficiency"]),
              help="Optimization objective")
@click.option("--target", help="Target value for optimization")
@click.pass_context
def optimize(ctx, agent_id: str, objective: str, target: Optional[str]):
    """Optimize multi-modal agent pipeline"""
    config = ctx.obj['config']
    
    optimization_data = {"objective": objective}
    if target:
        optimization_data["target"] = target
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/optimize",
                headers={"X-Api-Key": config.api_key or ""},
                json=optimization_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Multi-modal optimization completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to optimize agent: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def convert():
    """Cross-modal conversion operations"""
    pass


multimodal.add_command(convert)


@convert.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="Input file path")
@click.option("--output", "output_format", required=True, 
              type=click.Choice(["text", "image", "audio", "video"]),
              help="Output modality")
@click.option("--model", default="blip", help="Conversion model to use")
@click.option("--output-file", type=click.Path(), help="Output file path")
@click.pass_context
def convert(ctx, input_path: str, output_format: str, model: str, output_file: Optional[str]):
    """Convert between modalities"""
    config = ctx.obj['config']
    
    # Read input file
    try:
        with open(input_path, 'rb') as f:
            input_data = f.read()
    except Exception as e:
        error(f"Failed to read input file: {e}")
        return
    
    conversion_data = {
        "input": {
            "data": base64.b64encode(input_data).decode(),
            "mime_type": mimetypes.guess_type(input_path)[0] or "application/octet-stream",
            "filename": Path(input_path).name
        },
        "output_modality": output_format,
        "model": model
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/convert",
                headers={"X-Api-Key": config.api_key or ""},
                json=conversion_data
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if output_file and result.get("output_data"):
                    # Decode and save output
                    output_data = base64.b64decode(result["output_data"])
                    with open(output_file, 'wb') as f:
                        f.write(output_data)
                    success(f"Conversion output saved to {output_file}")
                else:
                    output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to convert modality: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def search():
    """Multi-modal search operations"""
    pass


multimodal.add_command(search)


@search.command()
@click.argument("query")
@click.option("--modalities", default="image,text", help="Comma-separated modalities to search")
@click.option("--limit", default=20, help="Number of results to return")
@click.option("--threshold", default=0.5, help="Similarity threshold")
@click.pass_context
def search(ctx, query: str, modalities: str, limit: int, threshold: float):
    """Multi-modal search across different modalities"""
    config = ctx.obj['config']
    
    search_data = {
        "query": query,
        "modalities": [m.strip() for m in modalities.split(',')],
        "limit": limit,
        "threshold": threshold
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/search",
                headers={"X-Api-Key": config.api_key or ""},
                json=search_data
            )
            
            if response.status_code == 200:
                results = response.json()
                output(results, ctx.obj['output_format'])
            else:
                error(f"Failed to perform multi-modal search: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def attention():
    """Cross-modal attention analysis"""
    pass


multimodal.add_command(attention)


@attention.command()
@click.argument("agent_id")
@click.option("--inputs", type=click.File('r'), required=True, help="Multi-modal inputs JSON file")
@click.option("--visualize", is_flag=True, help="Generate attention visualization")
@click.option("--output", type=click.Path(), help="Output file for visualization")
@click.pass_context
def attention(ctx, agent_id: str, inputs, visualize: bool, output: Optional[str]):
    """Analyze cross-modal attention patterns"""
    config = ctx.obj['config']
    
    try:
        inputs_data = json.load(inputs)
    except Exception as e:
        error(f"Failed to read inputs file: {e}")
        return
    
    attention_data = {
        "inputs": inputs_data,
        "visualize": visualize
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/attention",
                headers={"X-Api-Key": config.api_key or ""},
                json=attention_data
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if visualize and output and result.get("visualization"):
                    # Save visualization
                    viz_data = base64.b64decode(result["visualization"])
                    with open(output, 'wb') as f:
                        f.write(viz_data)
                    success(f"Attention visualization saved to {output}")
                else:
                    output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to analyze attention: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@multimodal.command()
@click.argument("agent_id")
@click.pass_context
def capabilities(ctx, agent_id: str):
    """List multi-modal agent capabilities"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/capabilities",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                capabilities = response.json()
                output(capabilities, ctx.obj['output_format'])
            else:
                error(f"Failed to get agent capabilities: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@multimodal.command()
@click.argument("agent_id")
@click.option("--modality", required=True, 
              type=click.Choice(["text", "image", "audio", "video"]),
              help="Modality to test")
@click.option("--test-data", type=click.File('r'), help="Test data JSON file")
@click.pass_context
def test(ctx, agent_id: str, modality: str, test_data):
    """Test individual modality processing"""
    config = ctx.obj['config']
    
    test_input = {}
    if test_data:
        try:
            test_input = json.load(test_data)
        except Exception as e:
            error(f"Failed to read test data file: {e}")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/multimodal/agents/{agent_id}/test/{modality}",
                headers={"X-Api-Key": config.api_key or ""},
                json=test_input
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Modality test completed for {modality}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to test modality: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)
