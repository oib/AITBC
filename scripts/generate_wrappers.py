#!/usr/bin/env python3
"""
Generate service wrapper scripts from template.
Run with: python scripts/generate_wrappers.py
"""

import os
import sys
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path("/opt/aitbc")
sys.path.insert(0, str(REPO_ROOT))

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Error: jinja2 not installed. Install with: pip install jinja2")
    sys.exit(1)

# Service configurations
SERVICES = [
    {
        "name": "coordinator-api",
        "module": "coordinator_api.main",
        "dir": "apps/coordinator-api",
    },
    {
        "name": "blockchain-node",
        "module": "aitbc_chain.main",
        "dir": "apps/blockchain-node",
    },
    {
        "name": "marketplace",
        "module": "marketplace_service.main",
        "dir": "apps/marketplace",
    },
    {
        "name": "wallet",
        "module": "app.main",
        "dir": "apps/wallet",
    },
    {
        "name": "agent-management",
        "module": "agent_management.main",
        "dir": "apps/agent-management",
    },
    {
        "name": "agent-coordinator",
        "module": "agent_coordinator.main",
        "dir": "apps/agent-coordinator",
    },
    {
        "name": "pool-hub",
        "module": "pool_hub.main",
        "dir": "apps/pool-hub",
    },
    {
        "name": "edge",
        "module": "edge_service.main",
        "dir": "apps/edge",
    },
    {
        "name": "hermes",
        "module": "hermes_service.main",
        "dir": "apps/hermes",
    },
    {
        "name": "gpu",
        "module": "gpu_service.main",
        "dir": "apps/gpu",
    },
    {
        "name": "trading",
        "module": "trading_service.main",
        "dir": "apps/trading",
    },
    {
        "name": "governance",
        "module": "governance_service.main",
        "dir": "apps/governance",
    },
]


def generate_wrapper(service_config: dict, template_env, output_dir: Path) -> None:
    """Generate a wrapper script for a service."""
    template = template_env.get_template("service-wrapper.py.j2")

    context = {
        "service_name": service_config["name"],
        "module_name": service_config["module"],
        "repo_dir": str(REPO_ROOT),
        "service_dir": str(REPO_ROOT / service_config["dir"]),
        "log_level": "INFO",
    }

    output_file = output_dir / f"{service_config['name']}-wrapper.py"
    rendered = template.render(context)

    with open(output_file, "w") as f:
        f.write(rendered)

    # Make executable
    os.chmod(output_file, 0o755)
    print(f"✓ Generated {output_file}")


def main():
    """Generate all service wrapper scripts."""
    print("Generating service wrapper scripts...")

    # Setup Jinja2 environment
    template_dir = REPO_ROOT / "scripts" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    # Create output directory
    output_dir = REPO_ROOT / "scripts" / "services"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate wrappers
    for service in SERVICES:
        try:
            generate_wrapper(service, env, output_dir)
        except Exception as e:
            print(f"✗ Failed to generate wrapper for {service['name']}: {e}")

    print(f"\nGenerated {len(SERVICES)} wrapper scripts to {output_dir}")
    print("\nTo use a wrapper:")
    print(f"  python {output_dir}/<service-name>-wrapper.py")


if __name__ == "__main__":
    main()
