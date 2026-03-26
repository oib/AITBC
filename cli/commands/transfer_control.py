"""Advanced transfer control commands for AITBC CLI"""

import click
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from utils import output, error, success, warning


@click.group()
def transfer_control():
    """Advanced transfer control and limit management commands"""
    pass


@transfer_control.command()
@click.option("--wallet", required=True, help="Wallet name or address")
@click.option("--max-daily", type=float, help="Maximum daily transfer amount")
@click.option("--max-weekly", type=float, help="Maximum weekly transfer amount")
@click.option("--max-monthly", type=float, help="Maximum monthly transfer amount")
@click.option("--max-single", type=float, help="Maximum single transfer amount")
@click.option("--whitelist", help="Comma-separated list of whitelisted addresses")
@click.option("--blacklist", help="Comma-separated list of blacklisted addresses")
@click.pass_context
def set_limit(ctx, wallet: str, max_daily: Optional[float], max_weekly: Optional[float], max_monthly: Optional[float], max_single: Optional[float], whitelist: Optional[str], blacklist: Optional[str]):
    """Set transfer limits for a wallet"""
    
    # Load existing limits
    limits_file = Path.home() / ".aitbc" / "transfer_limits.json"
    limits_file.parent.mkdir(parents=True, exist_ok=True)
    
    limits = {}
    if limits_file.exists():
        with open(limits_file, 'r') as f:
            limits = json.load(f)
    
    # Create or update wallet limits
    wallet_limits = limits.get(wallet, {
        "wallet": wallet,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "status": "active"
    })
    
    # Update limits
    if max_daily is not None:
        wallet_limits["max_daily"] = max_daily
    if max_weekly is not None:
        wallet_limits["max_weekly"] = max_weekly
    if max_monthly is not None:
        wallet_limits["max_monthly"] = max_monthly
    if max_single is not None:
        wallet_limits["max_single"] = max_single
    
    # Update whitelist and blacklist
    if whitelist:
        wallet_limits["whitelist"] = [addr.strip() for addr in whitelist.split(',')]
    if blacklist:
        wallet_limits["blacklist"] = [addr.strip() for addr in blacklist.split(',')]
    
    wallet_limits["updated_at"] = datetime.utcnow().isoformat()
    
    # Initialize usage tracking
    if "usage" not in wallet_limits:
        wallet_limits["usage"] = {
            "daily": {"amount": 0.0, "count": 0, "reset_at": datetime.utcnow().isoformat()},
            "weekly": {"amount": 0.0, "count": 0, "reset_at": datetime.utcnow().isoformat()},
            "monthly": {"amount": 0.0, "count": 0, "reset_at": datetime.utcnow().isoformat()}
        }
    
    # Save limits
    limits[wallet] = wallet_limits
    with open(limits_file, 'w') as f:
        json.dump(limits, f, indent=2)
    
    success(f"Transfer limits set for wallet '{wallet}'")
    output({
        "wallet": wallet,
        "limits": {
            "max_daily": wallet_limits.get("max_daily"),
            "max_weekly": wallet_limits.get("max_weekly"),
            "max_monthly": wallet_limits.get("max_monthly"),
            "max_single": wallet_limits.get("max_single")
        },
        "whitelist_count": len(wallet_limits.get("whitelist", [])),
        "blacklist_count": len(wallet_limits.get("blacklist", [])),
        "updated_at": wallet_limits["updated_at"]
    })


@transfer_control.command()
@click.option("--wallet", required=True, help="Wallet name or address")
@click.option("--amount", type=float, required=True, help="Amount to time-lock")
@click.option("--duration", type=int, required=True, help="Lock duration in days")
@click.option("--recipient", required=True, help="Recipient address")
@click.option("--description", help="Lock description")
@click.pass_context
def time_lock(ctx, wallet: str, amount: float, duration: int, recipient: str, description: Optional[str]):
    """Create a time-locked transfer"""
    
    # Generate lock ID
    lock_id = f"lock_{str(int(datetime.utcnow().timestamp()))[-8:]}"
    
    # Calculate release time
    release_time = datetime.utcnow() + timedelta(days=duration)
    
    # Create time lock
    time_lock = {
        "lock_id": lock_id,
        "wallet": wallet,
        "recipient": recipient,
        "amount": amount,
        "duration_days": duration,
        "created_at": datetime.utcnow().isoformat(),
        "release_time": release_time.isoformat(),
        "status": "locked",
        "description": description or f"Time-locked transfer of {amount} to {recipient}",
        "released_at": None,
        "released_amount": 0.0
    }
    
    # Store time lock
    timelocks_file = Path.home() / ".aitbc" / "time_locks.json"
    timelocks_file.parent.mkdir(parents=True, exist_ok=True)
    
    timelocks = {}
    if timelocks_file.exists():
        with open(timelocks_file, 'r') as f:
            timelocks = json.load(f)
    
    timelocks[lock_id] = time_lock
    
    with open(timelocks_file, 'w') as f:
        json.dump(timelocks, f, indent=2)
    
    success(f"Time-locked transfer created: {lock_id}")
    output({
        "lock_id": lock_id,
        "wallet": wallet,
        "recipient": recipient,
        "amount": amount,
        "duration_days": duration,
        "release_time": time_lock["release_time"],
        "status": "locked"
    })


@transfer_control.command()
@click.option("--wallet", required=True, help="Wallet name or address")
@click.option("--total-amount", type=float, required=True, help="Total amount to vest")
@click.option("--duration", type=int, required=True, help="Vesting duration in days")
@click.option("--cliff-period", type=int, default=0, help="Cliff period in days before any release")
@click.option("--release-interval", type=int, default=30, help="Release interval in days")
@click.option("--recipient", required=True, help="Recipient address")
@click.option("--description", help="Vesting schedule description")
@click.pass_context
def vesting_schedule(ctx, wallet: str, total_amount: float, duration: int, cliff_period: int, release_interval: int, recipient: str, description: Optional[str]):
    """Create a vesting schedule for token release"""
    
    # Generate schedule ID
    schedule_id = f"vest_{str(int(datetime.utcnow().timestamp()))[-8:]}"
    
    # Calculate vesting schedule
    start_time = datetime.utcnow() + timedelta(days=cliff_period)
    end_time = datetime.utcnow() + timedelta(days=duration)
    
    # Create release events
    releases = []
    current_time = start_time
    remaining_amount = total_amount
    
    while current_time <= end_time and remaining_amount > 0:
        releases.append({
            "release_time": current_time.isoformat(),
            "amount": total_amount / max(1, (duration - cliff_period) // release_interval),
            "released": False,
            "released_at": None
        })
        current_time += timedelta(days=release_interval)
    
    # Create vesting schedule
    vesting_schedule = {
        "schedule_id": schedule_id,
        "wallet": wallet,
        "recipient": recipient,
        "total_amount": total_amount,
        "duration_days": duration,
        "cliff_period_days": cliff_period,
        "release_interval_days": release_interval,
        "created_at": datetime.utcnow().isoformat(),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "status": "active",
        "description": description or f"Vesting {total_amount} over {duration} days",
        "releases": releases,
        "total_released": 0.0,
        "released_count": 0
    }
    
    # Store vesting schedule
    vesting_file = Path.home() / ".aitbc" / "vesting_schedules.json"
    vesting_file.parent.mkdir(parents=True, exist_ok=True)
    
    vesting_schedules = {}
    if vesting_file.exists():
        with open(vesting_file, 'r') as f:
            vesting_schedules = json.load(f)
    
    vesting_schedules[schedule_id] = vesting_schedule
    
    with open(vesting_file, 'w') as f:
        json.dump(vesting_schedules, f, indent=2)
    
    success(f"Vesting schedule created: {schedule_id}")
    output({
        "schedule_id": schedule_id,
        "wallet": wallet,
        "recipient": recipient,
        "total_amount": total_amount,
        "duration_days": duration,
        "cliff_period_days": cliff_period,
        "release_count": len(releases),
        "start_time": vesting_schedule["start_time"],
        "end_time": vesting_schedule["end_time"]
    })


@transfer_control.command()
@click.option("--wallet", help="Filter by wallet")
@click.option("--status", help="Filter by status")
@click.pass_context
def audit_trail(ctx, wallet: Optional[str], status: Optional[str]):
    """View complete transfer audit trail"""
    
    # Collect all transfer-related data
    audit_data = {
        "limits": {},
        "time_locks": {},
        "vesting_schedules": {},
        "transfers": {},
        "generated_at": datetime.utcnow().isoformat()
    }
    
    # Load transfer limits
    limits_file = Path.home() / ".aitbc" / "transfer_limits.json"
    if limits_file.exists():
        with open(limits_file, 'r') as f:
            limits = json.load(f)
        
        for wallet_id, limit_data in limits.items():
            if wallet and wallet_id != wallet:
                continue
            
            audit_data["limits"][wallet_id] = {
                "limits": {
                    "max_daily": limit_data.get("max_daily"),
                    "max_weekly": limit_data.get("max_weekly"),
                    "max_monthly": limit_data.get("max_monthly"),
                    "max_single": limit_data.get("max_single")
                },
                "usage": limit_data.get("usage", {}),
                "whitelist": limit_data.get("whitelist", []),
                "blacklist": limit_data.get("blacklist", []),
                "created_at": limit_data.get("created_at"),
                "updated_at": limit_data.get("updated_at")
            }
    
    # Load time locks
    timelocks_file = Path.home() / ".aitbc" / "time_locks.json"
    if timelocks_file.exists():
        with open(timelocks_file, 'r') as f:
            timelocks = json.load(f)
        
        for lock_id, lock_data in timelocks.items():
            if wallet and lock_data.get("wallet") != wallet:
                continue
            if status and lock_data.get("status") != status:
                continue
            
            audit_data["time_locks"][lock_id] = lock_data
    
    # Load vesting schedules
    vesting_file = Path.home() / ".aitbc" / "vesting_schedules.json"
    if vesting_file.exists():
        with open(vesting_file, 'r') as f:
            vesting_schedules = json.load(f)
        
        for schedule_id, schedule_data in vesting_schedules.items():
            if wallet and schedule_data.get("wallet") != wallet:
                continue
            if status and schedule_data.get("status") != status:
                continue
            
            audit_data["vesting_schedules"][schedule_id] = schedule_data
    
    # Generate summary
    audit_data["summary"] = {
        "total_wallets_with_limits": len(audit_data["limits"]),
        "total_time_locks": len(audit_data["time_locks"]),
        "total_vesting_schedules": len(audit_data["vesting_schedules"]),
        "filter_criteria": {
            "wallet": wallet or "all",
            "status": status or "all"
        }
    }
    
    output(audit_data)


@transfer_control.command()
@click.option("--wallet", help="Filter by wallet")
@click.pass_context
def status(ctx, wallet: Optional[str]):
    """Get transfer control status"""
    
    status_data = {
        "wallet_limits": {},
        "active_time_locks": {},
        "active_vesting_schedules": {},
        "generated_at": datetime.utcnow().isoformat()
    }
    
    # Load and filter limits
    limits_file = Path.home() / ".aitbc" / "transfer_limits.json"
    if limits_file.exists():
        with open(limits_file, 'r') as f:
            limits = json.load(f)
        
        for wallet_id, limit_data in limits.items():
            if wallet and wallet_id != wallet:
                continue
            
            # Check usage against limits
            daily_usage = limit_data.get("usage", {}).get("daily", {})
            weekly_usage = limit_data.get("usage", {}).get("weekly", {})
            monthly_usage = limit_data.get("usage", {}).get("monthly", {})
            
            status_data["wallet_limits"][wallet_id] = {
                "limits": {
                    "max_daily": limit_data.get("max_daily"),
                    "max_weekly": limit_data.get("max_weekly"),
                    "max_monthly": limit_data.get("max_monthly"),
                    "max_single": limit_data.get("max_single")
                },
                "current_usage": {
                    "daily": daily_usage,
                    "weekly": weekly_usage,
                    "monthly": monthly_usage
                },
                "status": limit_data.get("status"),
                "whitelist_count": len(limit_data.get("whitelist", [])),
                "blacklist_count": len(limit_data.get("blacklist", []))
            }
    
    # Load active time locks
    timelocks_file = Path.home() / ".aitbc" / "time_locks.json"
    if timelocks_file.exists():
        with open(timelocks_file, 'r') as f:
            timelocks = json.load(f)
        
        for lock_id, lock_data in timelocks.items():
            if wallet and lock_data.get("wallet") != wallet:
                continue
            if lock_data.get("status") == "locked":
                status_data["active_time_locks"][lock_id] = lock_data
    
    # Load active vesting schedules
    vesting_file = Path.home() / ".aitbc" / "vesting_schedules.json"
    if vesting_file.exists():
        with open(vesting_file, 'r') as f:
            vesting_schedules = json.load(f)
        
        for schedule_id, schedule_data in vesting_schedules.items():
            if wallet and schedule_data.get("wallet") != wallet:
                continue
            if schedule_data.get("status") == "active":
                status_data["active_vesting_schedules"][schedule_id] = schedule_data
    
    # Calculate totals
    status_data["summary"] = {
        "wallets_with_limits": len(status_data["wallet_limits"]),
        "active_time_locks": len(status_data["active_time_locks"]),
        "active_vesting_schedules": len(status_data["active_vesting_schedules"]),
        "filter_wallet": wallet or "all"
    }
    
    output(status_data)


@transfer_control.command()
@click.argument("lock_id")
@click.pass_context
def release_time_lock(ctx, lock_id: str):
    """Release a time-locked transfer (if time has passed)"""
    
    timelocks_file = Path.home() / ".aitbc" / "time_locks.json"
    if not timelocks_file.exists():
        error("No time-locked transfers found.")
        return
    
    with open(timelocks_file, 'r') as f:
        timelocks = json.load(f)
    
    if lock_id not in timelocks:
        error(f"Time lock '{lock_id}' not found.")
        return
    
    lock_data = timelocks[lock_id]
    
    # Check if lock can be released
    release_time = datetime.fromisoformat(lock_data["release_time"])
    current_time = datetime.utcnow()
    
    if current_time < release_time:
        error(f"Time lock cannot be released until {release_time.isoformat()}")
        return
    
    # Release the lock
    lock_data["status"] = "released"
    lock_data["released_at"] = current_time.isoformat()
    lock_data["released_amount"] = lock_data["amount"]
    
    # Save updated timelocks
    with open(timelocks_file, 'w') as f:
        json.dump(timelocks, f, indent=2)
    
    success(f"Time lock '{lock_id}' released")
    output({
        "lock_id": lock_id,
        "status": "released",
        "released_at": lock_data["released_at"],
        "released_amount": lock_data["released_amount"],
        "recipient": lock_data["recipient"]
    })


@transfer_control.command()
@click.argument("schedule_id")
@click.pass_context
def release_vesting(ctx, schedule_id: str):
    """Release available vesting amounts"""
    
    vesting_file = Path.home() / ".aitbc" / "vesting_schedules.json"
    if not vesting_file.exists():
        error("No vesting schedules found.")
        return
    
    with open(vesting_file, 'r') as f:
        vesting_schedules = json.load(f)
    
    if schedule_id not in vesting_schedules:
        error(f"Vesting schedule '{schedule_id}' not found.")
        return
    
    schedule = vesting_schedules[schedule_id]
    current_time = datetime.utcnow()
    
    # Find available releases
    available_releases = []
    total_available = 0.0
    
    for release in schedule["releases"]:
        if not release["released"]:
            release_time = datetime.fromisoformat(release["release_time"])
            if current_time >= release_time:
                available_releases.append(release)
                total_available += release["amount"]
    
    if not available_releases:
        warning("No vesting amounts available for release at this time.")
        return
    
    # Mark releases as released
    for release in available_releases:
        release["released"] = True
        release["released_at"] = current_time.isoformat()
    
    # Update schedule totals
    schedule["total_released"] += total_available
    schedule["released_count"] += len(available_releases)
    
    # Check if schedule is complete
    if schedule["released_count"] == len(schedule["releases"]):
        schedule["status"] = "completed"
    
    # Save updated schedules
    with open(vesting_file, 'w') as f:
        json.dump(vesting_schedules, f, indent=2)
    
    success(f"Released {total_available} from vesting schedule '{schedule_id}'")
    output({
        "schedule_id": schedule_id,
        "released_amount": total_available,
        "releases_count": len(available_releases),
        "total_released": schedule["total_released"],
        "schedule_status": schedule["status"]
    })
