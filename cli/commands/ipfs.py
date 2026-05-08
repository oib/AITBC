"""IPFS storage and retrieval commands for AITBC CLI"""

import click
import json
from pathlib import Path
from typing import Optional
from utils import output, error, success, warning

@click.group()
def ipfs():
    """IPFS distributed storage commands"""
    pass

@ipfs.command()
@click.option("--file", type=click.Path(exists=True), required=True, help="File to upload")
@click.option("--pin", is_flag=True, default=False, help="Pin the content")
@click.option("--name", help="Optional name for the content")
def upload(file: str, pin: bool, name: Optional[str]):
    """Upload file to IPFS"""
    try:
        file_path = Path(file)
        
        # For demo purposes, generate a pseudo CID
        # In production, this would call actual IPFS service
        import hashlib
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Generate pseudo CID based on file hash
        file_hash = hashlib.sha256(data).hexdigest()
        cid = f"Qm{file_hash[:44]}"
        
        # Store in local demo storage
        storage_dir = Path.home() / ".aitbc"
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        ipfs_data = {
            "cid": cid,
            "name": name or file_path.name,
            "size": len(data),
            "pinned": pin,
            "file_path": str(file_path),
            "timestamp": str(Path(file_path).stat().st_mtime)
        }
        
        ipfs_file = storage_dir / "ipfs_storage.json"
        ipfs_storage = {}
        if ipfs_file.exists():
            with open(ipfs_file, 'r') as f:
                ipfs_storage = json.load(f)
        
        ipfs_storage[cid] = ipfs_data
        
        with open(ipfs_file, 'w') as f:
            json.dump(ipfs_storage, f, indent=2)
        
        success(f"File uploaded to IPFS")
        output({
            "cid": cid,
            "name": ipfs_data["name"],
            "size": ipfs_data["size"],
            "pinned": pin
        })
        
    except Exception as e:
        error(f"Failed to upload file: {e}")

@ipfs.command()
@click.argument("cid")
@click.option("--output", type=click.Path(), help="Output file path")
def download(cid: str, output: Optional[str]):
    """Download file from IPFS by CID"""
    try:
        storage_dir = Path.home() / ".aitbc"
        ipfs_file = storage_dir / "ipfs_storage.json"
        
        if not ipfs_file.exists():
            error("IPFS storage not found")
            return
        
        with open(ipfs_file, 'r') as f:
            ipfs_storage = json.load(f)
        
        if cid not in ipfs_storage:
            error(f"CID {cid} not found in local storage")
            return
        
        ipfs_data = ipfs_storage[cid]
        file_path = Path(ipfs_data["file_path"])
        
        if not file_path.exists():
            error(f"Original file {file_path} no longer exists")
            return
        
        # Copy to output path if specified
        if output:
            import shutil
            shutil.copy(file_path, output)
            success(f"File downloaded to {output}")
        else:
            success(f"File retrieved from {file_path}")
        
        output({
            "cid": cid,
            "name": ipfs_data["name"],
            "size": ipfs_data["size"],
            "file_path": str(file_path)
        })
        
    except Exception as e:
        error(f"Failed to download file: {e}")

@ipfs.command()
@click.argument("cid")
def pin(cid: str):
    """Pin content to IPFS"""
    try:
        storage_dir = Path.home() / ".aitbc"
        ipfs_file = storage_dir / "ipfs_storage.json"
        
        if not ipfs_file.exists():
            error("IPFS storage not found")
            return
        
        with open(ipfs_file, 'r') as f:
            ipfs_storage = json.load(f)
        
        if cid not in ipfs_storage:
            error(f"CID {cid} not found in local storage")
            return
        
        ipfs_storage[cid]["pinned"] = True
        
        with open(ipfs_file, 'w') as f:
            json.dump(ipfs_storage, f, indent=2)
        
        success(f"CID {cid} pinned")
        output({"cid": cid, "pinned": True})
        
    except Exception as e:
        error(f"Failed to pin CID: {e}")

@ipfs.command()
def list():
    """List all stored IPFS content"""
    try:
        storage_dir = Path.home() / ".aitbc"
        ipfs_file = storage_dir / "ipfs_storage.json"
        
        if not ipfs_file.exists():
            warning("No IPFS storage found")
            return
        
        with open(ipfs_file, 'r') as f:
            ipfs_storage = json.load(f)
        
        output({
            "total": len(ipfs_storage),
            "items": [
                {
                    "cid": cid,
                    "name": data["name"],
                    "size": data["size"],
                    "pinned": data["pinned"]
                }
                for cid, data in ipfs_storage.items()
            ]
        })
        
    except Exception as e:
        error(f"Failed to list IPFS content: {e}")
