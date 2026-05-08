"""Island computing commands for AITBC CLI"""

import click
from utils import output, error, success, warning


@click.group()
def island():
    """Island computing commands"""
    pass


@island.command()
@click.option("--name", required=True, help="Island name")
@click.option("--capacity", type=int, help="Computing capacity")
def create(name: str, capacity: int):
    """Create island"""
    import uuid
    output({
        "island_id": f"island_{uuid.uuid4().hex[:16]}",
        "name": name,
        "capacity": capacity or 100,
        "status": "active"
    })


@island.command()
@click.option("--island-id", required=True, help="Island ID")
def join(island_id: str):
    """Join island"""
    output({
        "island_id": island_id,
        "status": "joined"
    })


@island.command()
@click.option("--island-id", required=True, help="Island ID")
def leave(island_id: str):
    """Leave island"""
    output({
        "island_id": island_id,
        "status": "left"
    })


@island.command()
@click.option("--source-island", required=True, help="Source island ID")
@click.option("--target-island", required=True, help="Target island ID")
@click.option("--bandwidth", type=int, help="Bridge bandwidth")
def bridge(source_island: str, target_island: str, bandwidth: int):
    """Create bridge between islands"""
    import uuid
    output({
        "bridge_id": f"bridge_{uuid.uuid4().hex[:16]}",
        "source_island": source_island,
        "target_island": target_island,
        "bandwidth": bandwidth or 1000,
        "status": "active"
    })
