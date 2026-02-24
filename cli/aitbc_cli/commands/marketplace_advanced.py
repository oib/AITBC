"""Advanced marketplace commands for AITBC CLI - Enhanced marketplace operations"""

import click
import httpx
import json
import base64
from typing import Optional, Dict, Any, List
from pathlib import Path
from ..utils import output, error, success, warning


@click.group()
def advanced():
    """Advanced marketplace operations and analytics"""
    pass


@click.group()
def models():
    """Advanced model NFT operations"""
    pass


advanced.add_command(models)


@models.command()
@click.option("--nft-version", default="2.0", help="NFT version filter")
@click.option("--category", help="Filter by model category")
@click.option("--tags", help="Comma-separated tags to filter")
@click.option("--rating-min", type=float, help="Minimum rating filter")
@click.option("--limit", default=20, help="Number of models to list")
@click.pass_context
def list(ctx, nft_version: str, category: Optional[str], tags: Optional[str], 
         rating_min: Optional[float], limit: int):
    """List advanced NFT models"""
    config = ctx.obj['config']
    
    params = {"nft_version": nft_version, "limit": limit}
    if category:
        params["category"] = category
    if tags:
        params["tags"] = [t.strip() for t in tags.split(',')]
    if rating_min:
        params["rating_min"] = rating_min
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/advanced/models",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                models = response.json()
                output(models, ctx.obj['output_format'])
            else:
                error(f"Failed to list models: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@models.command()
@click.option("--model-file", type=click.Path(exists=True), required=True, help="Model file path")
@click.option("--metadata", type=click.File('r'), required=True, help="Model metadata JSON file")
@click.option("--price", type=float, help="Initial price")
@click.option("--royalty", type=float, default=0.0, help="Royalty percentage")
@click.option("--supply", default=1, help="NFT supply")
@click.pass_context
def mint(ctx, model_file: str, metadata, price: Optional[float], royalty: float, supply: int):
    """Create model NFT with advanced metadata"""
    config = ctx.obj['config']
    
    # Read model file
    try:
        with open(model_file, 'rb') as f:
            model_data = f.read()
    except Exception as e:
        error(f"Failed to read model file: {e}")
        return
    
    # Read metadata
    try:
        metadata_data = json.load(metadata)
    except Exception as e:
        error(f"Failed to read metadata file: {e}")
        return
    
    nft_data = {
        "metadata": metadata_data,
        "royalty_percentage": royalty,
        "supply": supply
    }
    
    if price:
        nft_data["initial_price"] = price
    
    files = {
        "model": model_data
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/models/mint",
                headers={"X-Api-Key": config.api_key or ""},
                data=nft_data,
                files=files
            )
            
            if response.status_code == 201:
                nft = response.json()
                success(f"Model NFT minted: {nft['id']}")
                output(nft, ctx.obj['output_format'])
            else:
                error(f"Failed to mint NFT: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@models.command()
@click.argument("nft_id")
@click.option("--new-version", type=click.Path(exists=True), required=True, help="New model version file")
@click.option("--version-notes", default="", help="Version update notes")
@click.option("--compatibility", default="backward", 
              type=click.Choice(["backward", "forward", "breaking"]),
              help="Compatibility type")
@click.pass_context
def update(ctx, nft_id: str, new_version: str, version_notes: str, compatibility: str):
    """Update model NFT with new version"""
    config = ctx.obj['config']
    
    # Read new version file
    try:
        with open(new_version, 'rb') as f:
            version_data = f.read()
    except Exception as e:
        error(f"Failed to read version file: {e}")
        return
    
    update_data = {
        "version_notes": version_notes,
        "compatibility": compatibility
    }
    
    files = {
        "version": version_data
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/models/{nft_id}/update",
                headers={"X-Api-Key": config.api_key or ""},
                data=update_data,
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Model NFT updated: {result['version']}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to update NFT: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@models.command()
@click.argument("nft_id")
@click.option("--deep-scan", is_flag=True, help="Perform deep authenticity scan")
@click.option("--check-integrity", is_flag=True, help="Check model integrity")
@click.option("--verify-performance", is_flag=True, help="Verify performance claims")
@click.pass_context
def verify(ctx, nft_id: str, deep_scan: bool, check_integrity: bool, verify_performance: bool):
    """Verify model authenticity and quality"""
    config = ctx.obj['config']
    
    verify_data = {
        "deep_scan": deep_scan,
        "check_integrity": check_integrity,
        "verify_performance": verify_performance
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/models/{nft_id}/verify",
                headers={"X-Api-Key": config.api_key or ""},
                json=verify_data
            )
            
            if response.status_code == 200:
                verification = response.json()
                
                if verification.get("authentic"):
                    success("Model authenticity: VERIFIED")
                else:
                    warning("Model authenticity: FAILED")
                
                output(verification, ctx.obj['output_format'])
            else:
                error(f"Failed to verify model: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def analytics():
    """Marketplace analytics and insights"""
    pass


advanced.add_command(analytics)


@analytics.command()
@click.option("--period", default="30d", help="Time period (1d, 7d, 30d, 90d)")
@click.option("--metrics", default="volume,trends", help="Comma-separated metrics")
@click.option("--category", help="Filter by category")
@click.option("--format", "output_format", default="json", 
              type=click.Choice(["json", "csv", "pdf"]),
              help="Output format")
@click.pass_context
def analytics(ctx, period: str, metrics: str, category: Optional[str], output_format: str):
    """Get comprehensive marketplace analytics"""
    config = ctx.obj['config']
    
    params = {
        "period": period,
        "metrics": [m.strip() for m in metrics.split(',')],
        "format": output_format
    }
    
    if category:
        params["category"] = category
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/advanced/analytics",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                if output_format == "pdf":
                    # Handle PDF download
                    filename = f"marketplace_analytics_{period}.pdf"
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    success(f"Analytics report downloaded: {filename}")
                else:
                    analytics_data = response.json()
                    output(analytics_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get analytics: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@analytics.command()
@click.argument("model_id")
@click.option("--competitors", is_flag=True, help="Include competitor analysis")
@click.option("--datasets", default="standard", help="Test datasets to use")
@click.option("--iterations", default=100, help="Benchmark iterations")
@click.pass_context
def benchmark(ctx, model_id: str, competitors: bool, datasets: str, iterations: int):
    """Model performance benchmarking"""
    config = ctx.obj['config']
    
    benchmark_data = {
        "competitors": competitors,
        "datasets": datasets,
        "iterations": iterations
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/models/{model_id}/benchmark",
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


@analytics.command()
@click.option("--category", help="Filter by category")
@click.option("--forecast", default="7d", help="Forecast period")
@click.option("--confidence", default=0.8, help="Confidence threshold")
@click.pass_context
def trends(ctx, category: Optional[str], forecast: str, confidence: float):
    """Market trend analysis and forecasting"""
    config = ctx.obj['config']
    
    params = {
        "forecast_period": forecast,
        "confidence_threshold": confidence
    }
    
    if category:
        params["category"] = category
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/advanced/trends",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                trends_data = response.json()
                output(trends_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get trends: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@analytics.command()
@click.option("--format", default="pdf", type=click.Choice(["pdf", "html", "json"]),
              help="Report format")
@click.option("--email", help="Email address to send report")
@click.option("--sections", default="all", help="Comma-separated report sections")
@click.pass_context
def report(ctx, format: str, email: Optional[str], sections: str):
    """Generate comprehensive marketplace report"""
    config = ctx.obj['config']
    
    report_data = {
        "format": format,
        "sections": [s.strip() for s in sections.split(',')]
    }
    
    if email:
        report_data["email"] = email
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/reports/generate",
                headers={"X-Api-Key": config.api_key or ""},
                json=report_data
            )
            
            if response.status_code == 202:
                report_job = response.json()
                success(f"Report generation started: {report_job['id']}")
                output(report_job, ctx.obj['output_format'])
            else:
                error(f"Failed to generate report: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def trading():
    """Advanced trading features"""
    pass


advanced.add_command(trading)


@trading.command()
@click.argument("auction_id")
@click.option("--amount", type=float, required=True, help="Bid amount")
@click.option("--max-auto-bid", type=float, help="Maximum auto-bid amount")
@click.option("--proxy", is_flag=True, help="Use proxy bidding")
@click.pass_context
def bid(ctx, auction_id: str, amount: float, max_auto_bid: Optional[float], proxy: bool):
    """Participate in model auction"""
    config = ctx.obj['config']
    
    bid_data = {
        "amount": amount,
        "proxy_bidding": proxy
    }
    
    if max_auto_bid:
        bid_data["max_auto_bid"] = max_auto_bid
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/auctions/{auction_id}/bid",
                headers={"X-Api-Key": config.api_key or ""},
                json=bid_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Bid placed successfully")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to place bid: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@trading.command()
@click.argument("model_id")
@click.option("--recipients", required=True, help="Comma-separated recipient:percentage pairs")
@click.option("--smart-contract", is_flag=True, help="Use smart contract distribution")
@click.pass_context
def royalties(ctx, model_id: str, recipients: str, smart_contract: bool):
    """Create royalty distribution agreement"""
    config = ctx.obj['config']
    
    # Parse recipients
    royalty_recipients = []
    for recipient in recipients.split(','):
        if ':' in recipient:
            address, percentage = recipient.split(':', 1)
            royalty_recipients.append({
                "address": address.strip(),
                "percentage": float(percentage.strip())
            })
    
    royalty_data = {
        "recipients": royalty_recipients,
        "smart_contract": smart_contract
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/models/{model_id}/royalties",
                headers={"X-Api-Key": config.api_key or ""},
                json=royalty_data
            )
            
            if response.status_code == 201:
                result = response.json()
                success(f"Royalty agreement created: {result['id']}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to create royalty agreement: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@trading.command()
@click.option("--strategy", default="arbitrage", 
              type=click.Choice(["arbitrage", "trend-following", "mean-reversion", "custom"]),
              help="Trading strategy")
@click.option("--budget", type=float, required=True, help="Trading budget")
@click.option("--risk-level", default="medium", 
              type=click.Choice(["low", "medium", "high"]),
              help="Risk level")
@click.option("--config", type=click.File('r'), help="Custom strategy configuration")
@click.pass_context
def execute(ctx, strategy: str, budget: float, risk_level: str, config):
    """Execute complex trading strategy"""
    config_obj = ctx.obj['config']
    
    strategy_data = {
        "strategy": strategy,
        "budget": budget,
        "risk_level": risk_level
    }
    
    if config:
        try:
            custom_config = json.load(config)
            strategy_data["custom_config"] = custom_config
        except Exception as e:
            error(f"Failed to read strategy config: {e}")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config_obj.coordinator_url}/v1/marketplace/advanced/trading/execute",
                headers={"X-Api-Key": config_obj.api_key or ""},
                json=strategy_data
            )
            
            if response.status_code == 202:
                execution = response.json()
                success(f"Trading strategy execution started: {execution['id']}")
                output(execution, ctx.obj['output_format'])
            else:
                error(f"Failed to execute strategy: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def dispute():
    """Dispute resolution operations"""
    pass


advanced.add_command(dispute)


@dispute.command()
@click.argument("transaction_id")
@click.option("--reason", required=True, help="Dispute reason")
@click.option("--evidence", type=click.File('rb'), multiple=True, help="Evidence files")
@click.option("--category", default="quality", 
              type=click.Choice(["quality", "delivery", "payment", "fraud", "other"]),
              help="Dispute category")
@click.pass_context
def file(ctx, transaction_id: str, reason: str, evidence, category: str):
    """File dispute resolution request"""
    config = ctx.obj['config']
    
    dispute_data = {
        "transaction_id": transaction_id,
        "reason": reason,
        "category": category
    }
    
    files = {}
    for i, evidence_file in enumerate(evidence):
        files[f"evidence_{i}"] = evidence_file.read()
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/disputes",
                headers={"X-Api-Key": config.api_key or ""},
                data=dispute_data,
                files=files
            )
            
            if response.status_code == 201:
                dispute = response.json()
                success(f"Dispute filed: {dispute['id']}")
                output(dispute, ctx.obj['output_format'])
            else:
                error(f"Failed to file dispute: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@dispute.command()
@click.argument("dispute_id")
@click.pass_context
def status(ctx, dispute_id: str):
    """Get dispute status and progress"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/marketplace/advanced/disputes/{dispute_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                dispute_data = response.json()
                output(dispute_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get dispute status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@dispute.command()
@click.argument("dispute_id")
@click.option("--resolution", required=True, help="Proposed resolution")
@click.option("--evidence", type=click.File('rb'), multiple=True, help="Additional evidence")
@click.pass_context
def resolve(ctx, dispute_id: str, resolution: str, evidence):
    """Propose dispute resolution"""
    config = ctx.obj['config']
    
    resolution_data = {
        "resolution": resolution
    }
    
    files = {}
    for i, evidence_file in enumerate(evidence):
        files[f"evidence_{i}"] = evidence_file.read()
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/marketplace/advanced/disputes/{dispute_id}/resolve",
                headers={"X-Api-Key": config.api_key or ""},
                data=resolution_data,
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Resolution proposal submitted")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to submit resolution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)
