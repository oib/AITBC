#!/usr/bin/env python3
"""
AITBC Miner CLI Extension
Adds comprehensive miner management commands to AITBC CLI
"""

import sys
import os
import argparse
from pathlib import Path

# Add the CLI directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from miner_management import miner_cli_dispatcher
except ImportError:
    print("❌ Error: miner_management module not found")
    sys.exit(1)


def main():
    """Main CLI entry point for miner management"""
    parser = argparse.ArgumentParser(
        description="AITBC AI Compute Miner Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register as AI compute provider
  python miner_cli.py register --miner-id ai-miner-1 --wallet ait1xyz --gpu-memory 8192 --models qwen3:8b llama3:8b --pricing 0.50

  # Check miner status
  python miner_cli.py status --miner-id ai-miner-1

  # Poll for jobs
  python miner_cli.py poll --miner-id ai-miner-1 --max-wait 60

  # Submit job result
  python miner_cli.py result --job-id job123 --miner-id ai-miner-1 --result "Job completed successfully" --success

  # List marketplace offers
  python miner_cli.py marketplace list --region us-west

  # Create marketplace offer
  python miner_cli.py marketplace create --miner-id ai-miner-1 --price 0.75 --capacity 2
        """
    )
    
    parser.add_argument("--coordinator-url", default="http://localhost:8011", 
                       help="Coordinator API URL")
    parser.add_argument("--api-key", default="miner_prod_key_use_real_value",
                       help="Miner API key")
    
    subparsers = parser.add_subparsers(dest="action", help="Miner management actions")
    
    # Register command
    register_parser = subparsers.add_parser("register", help="Register as AI compute provider")
    register_parser.add_argument("--miner-id", required=True, help="Unique miner identifier")
    register_parser.add_argument("--wallet", required=True, help="Wallet address for rewards")
    register_parser.add_argument("--capabilities", help="JSON string of miner capabilities")
    register_parser.add_argument("--gpu-memory", type=int, help="GPU memory in MB")
    register_parser.add_argument("--models", nargs="+", help="Supported AI models")
    register_parser.add_argument("--pricing", type=float, help="Price per hour")
    register_parser.add_argument("--concurrency", type=int, default=1, help="Max concurrent jobs")
    register_parser.add_argument("--region", help="Geographic region")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get miner status")
    status_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    
    # Heartbeat command
    heartbeat_parser = subparsers.add_parser("heartbeat", help="Send miner heartbeat")
    heartbeat_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    heartbeat_parser.add_argument("--inflight", type=int, default=0, help="Currently running jobs")
    heartbeat_parser.add_argument("--status", default="ONLINE", help="Miner status")
    
    # Poll command
    poll_parser = subparsers.add_parser("poll", help="Poll for available jobs")
    poll_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    poll_parser.add_argument("--max-wait", type=int, default=30, help="Max wait time in seconds")
    poll_parser.add_argument("--auto-execute", action="store_true", help="Automatically execute assigned jobs")
    
    # Result command
    result_parser = subparsers.add_parser("result", help="Submit job result")
    result_parser.add_argument("--job-id", required=True, help="Job identifier")
    result_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    result_parser.add_argument("--result", help="Job result (JSON string)")
    result_parser.add_argument("--result-file", help="File containing job result")
    result_parser.add_argument("--success", action="store_true", help="Job completed successfully")
    result_parser.add_argument("--duration", type=int, help="Job duration in milliseconds")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update miner capabilities")
    update_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    update_parser.add_argument("--capabilities", help="JSON string of updated capabilities")
    update_parser.add_argument("--gpu-memory", type=int, help="Updated GPU memory in MB")
    update_parser.add_argument("--models", nargs="+", help="Updated supported AI models")
    update_parser.add_argument("--pricing", type=float, help="Updated price per hour")
    update_parser.add_argument("--concurrency", type=int, help="Updated max concurrent jobs")
    update_parser.add_argument("--region", help="Updated geographic region")
    update_parser.add_argument("--wallet", help="Updated wallet address")
    
    # Earnings command
    earnings_parser = subparsers.add_parser("earnings", help="Check miner earnings")
    earnings_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    earnings_parser.add_argument("--period", choices=["day", "week", "month", "all"], default="all", help="Earnings period")
    
    # Marketplace commands
    marketplace_parser = subparsers.add_parser("marketplace", help="Manage marketplace offers")
    marketplace_subparsers = marketplace_parser.add_subparsers(dest="marketplace_action", help="Marketplace actions")
    
    # Marketplace list
    market_list_parser = marketplace_subparsers.add_parser("list", help="List marketplace offers")
    market_list_parser.add_argument("--miner-id", help="Filter by miner ID")
    market_list_parser.add_argument("--region", help="Filter by region")
    
    # Marketplace create
    market_create_parser = marketplace_subparsers.add_parser("create", help="Create marketplace offer")
    market_create_parser.add_argument("--miner-id", required=True, help="Miner identifier")
    market_create_parser.add_argument("--price", type=float, required=True, help="Offer price per hour")
    market_create_parser.add_argument("--capacity", type=int, default=1, help="Available capacity")
    market_create_parser.add_argument("--region", help="Geographic region")
    
    args = parser.parse_args()
    
    if not args.action:
        parser.print_help()
        return
    
    # Initialize action variable
    action = args.action
    
    # Prepare kwargs for the dispatcher
    kwargs = {
        "coordinator_url": args.coordinator_url,
        "api_key": args.api_key
    }
    
    # Add action-specific arguments
    if args.action == "register":
        kwargs.update({
            "miner_id": args.miner_id,
            "wallet": args.wallet,
            "capabilities": args.capabilities,
            "gpu_memory": args.gpu_memory,
            "models": args.models,
            "pricing": args.pricing,
            "concurrency": args.concurrency,
            "region": args.region
        })
    
    elif args.action == "status":
        kwargs["miner_id"] = args.miner_id
    
    elif args.action == "heartbeat":
        kwargs.update({
            "miner_id": args.miner_id,
            "inflight": args.inflight,
            "status": args.status
        })
    
    elif args.action == "poll":
        kwargs.update({
            "miner_id": args.miner_id,
            "max_wait": args.max_wait,
            "auto_execute": args.auto_execute
        })
    
    elif args.action == "result":
        kwargs.update({
            "job_id": args.job_id,
            "miner_id": args.miner_id,
            "result": args.result,
            "result_file": args.result_file,
            "success": args.success,
            "duration": args.duration
        })
    
    elif args.action == "update":
        kwargs.update({
            "miner_id": args.miner_id,
            "capabilities": args.capabilities,
            "gpu_memory": args.gpu_memory,
            "models": args.models,
            "pricing": args.pricing,
            "concurrency": args.concurrency,
            "region": args.region,
            "wallet": args.wallet
        })
    
    elif args.action == "earnings":
        kwargs.update({
            "miner_id": args.miner_id,
            "period": args.period
        })
    
    elif args.action == "marketplace":
        action = args.action
        if args.marketplace_action == "list":
            kwargs.update({
                "miner_id": getattr(args, 'miner_id', None),
                "region": getattr(args, 'region', None)
            })
            action = "marketplace_list"
        elif args.marketplace_action == "create":
            kwargs.update({
                "miner_id": args.miner_id,
                "price": args.price,
                "capacity": args.capacity,
                "region": getattr(args, 'region', None)
            })
            action = "marketplace_create"
        else:
            print("❌ Unknown marketplace action")
            return
    
    result = miner_cli_dispatcher(action, **kwargs)
    
    # Display results
    if result:
        print("\n" + "="*60)
        print(f"🤖 AITBC Miner Management - {action.upper()}")
        print("="*60)
        
        if "status" in result:
            print(f"Status: {result['status']}")
        
        if result.get("status", "").startswith("✅"):
            # Success - show details
            for key, value in result.items():
                if key not in ["action", "status"]:
                    if isinstance(value, (dict, list)):
                        print(f"{key}:")
                        if isinstance(value, dict):
                            for k, v in value.items():
                                print(f"  {k}: {v}")
                        else:
                            for item in value:
                                print(f"  - {item}")
                    else:
                        print(f"{key}: {value}")
        else:
            # Error or info - show all relevant fields
            for key, value in result.items():
                if key != "action":
                    print(f"{key}: {value}")
        
        print("="*60)
    else:
        print("❌ No response from server")


if __name__ == "__main__":
    main()
