#!/usr/bin/env python3
"""
Generate service wrapper scripts from template.
Usage: python scripts/generate_wrappers.py
"""

import os
from pathlib import Path
from string import Template

# Service configurations
SERVICES = [
    {
        "name": "agent-coordinator",
        "type": "uvicorn",
        "module": "app.main:app",
        "bind_host_env": "AGENT_COORDINATOR_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "AGENT_COORDINATOR_PORT",
        "port_default": "8107",
        "extra_paths": ["agent-coordinator/scripts"],
    },
    {
        "name": "coordinator-api",
        "type": "uvicorn",
        "module": "app.main:app",
        "bind_host_env": "COORDINATOR_API_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "COORDINATOR_API_PORT",
        "port_default": "8203",
        "extra_paths": ["coordinator-api/src"],
        "workers": "1",
        "extra_uvicorn_args": ["--timeout-keep-alive", "30", "--limit-concurrency", "100", "--backlog", "256"],
    },
    {
        "name": "marketplace",
        "type": "script",
        "script_path": "marketplace.py",
        "extra_paths": [
            "marketplace/scripts",
            "marketplace/src",
            "coordinator-api/src",
            "packages/py/aitbc-sdk/src",
            "packages/py/aitbc-crypto/src",
        ],
    },
    {
        "name": "wallet",
        "type": "uvicorn",
        "module": "app.main:app",
        "bind_host_env": "WALLET_BIND_HOST",
        "bind_host_default": "0.0.0.0",
        "port_env": "WALLET_BIND_PORT",
        "port_default": "8108",
        "extra_paths": [
            "wallet/src",
            "packages/py/aitbc-crypto/src",
            "packages/py/aitbc-sdk/src",
        ],
        "wallet_dir_env": "WALLET_DIR",
    },
    {
        "name": "hermes",
        "type": "uvicorn",
        "module": "hermes_service.main:app",
        "bind_host_env": "HERMES_BIND_HOST",
        "bind_host_default": "0.0.0.0",
        "port_env": "HERMES_BIND_PORT",
        "port_default": "8103",
        "extra_paths": ["hermes/src"],
        "load_node_env": True,
        "db_path": "data/hermes_coin_requests.db",
        "db_path_env": "HERMES_DB_PATH",
    },
    {
        "name": "gpu",
        "type": "uvicorn",
        "module": "gpu_service.main:app",
        "bind_host_env": "GPU_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "GPU_BIND_PORT",
        "port_default": "8102",
        "extra_paths": ["gpu/src"],
    },
    {
        "name": "trading",
        "type": "uvicorn",
        "module": "trading_service.main:app",
        "bind_host_env": "TRADING_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "TRADING_BIND_PORT",
        "port_default": "8104",
        "extra_paths": ["trading/src"],
    },
    {
        "name": "governance",
        "type": "uvicorn",
        "module": "governance_service.main:app",
        "bind_host_env": "GOVERNANCE_BIND_HOST",
        "bind_host_default": "0.0.0.0",
        "port_env": "GOVERNANCE_BIND_PORT",
        "port_default": "8105",
        "extra_paths": ["governance/src"],
    },
    {
        "name": "agent-registry",
        "type": "uvicorn",
        "module": "app.main:app",
        "bind_host_env": "AGENT_REGISTRY_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "AGENT_REGISTRY_PORT",
        "port_default": "8012",
        "extra_paths": ["agent-management/src"],
    },
    {
        "name": "agent-management",
        "type": "uvicorn",
        "module": "app.main:app",
        "bind_host_env": "AGENT_MANAGEMENT_BIND_HOST",
        "bind_host_default": "127.0.0.1",
        "port_env": "AGENT_MANAGEMENT_PORT",
        "port_default": "8204",
        "extra_paths": ["agent-management/src"],
    },
]

UVICORN_TEMPLATE = '''#!/usr/bin/env python3
"""
Wrapper script for {service_name} service
Uses centralized aitbc utilities for path configuration
"""

import os
from pathlib import Path
from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR, KEYSTORE_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "{PYTHONPATH}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

{wallet_env_code}

{load_node_env_code}

{db_path_code}

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# {service_name} bind configuration
# Use {bind_host_env} for bind address (default: {bind_host_default})
# Use {port_env} for port (default: {port_default})
bind_host = os.getenv("{bind_host_env}", "{bind_host_default}")
bind_port = os.getenv("{port_env}", "{port_default}")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "{module}",
    "--host",
    bind_host,
    "--port",
    bind_port,
{workers_code}{extra_uvicorn_code}
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
'''

SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""
Wrapper script for {service_name} service
Uses centralized aitbc utilities for path configuration
"""

import os
from pathlib import Path
from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR, KEYSTORE_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "{PYTHONPATH}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

{load_node_env_code}

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "{script_path}",
]
os.execvp(exec_cmd[0], exec_cmd)
'''


def main():
    output_dir = Path("apps")

    for service in SERVICES:
        name = service["name"]

        # Build PYTHONPATH
        pythonpath_parts = ["REPO_DIR"]
        if "extra_paths" in service:
            for path in service["extra_paths"]:
                pythonpath_parts.append(f"REPO_DIR/{path}")
        pythonpath = ":".join(pythonpath_parts)

        # Prepare wallet code
        wallet_env_code = ""
        if "wallet_dir_env" in service:
            wallet_env_code = f'wallet_dir = os.getenv("{service["wallet_dir_env"]}")\nif wallet_dir:\n    os.environ["WALLET_DIR"] = wallet_dir'

        # Prepare node env loading code
        load_node_env_code = ""
        if service.get("load_node_env"):
            load_node_env_code = """# Load node.env to get additional config
if os.path.exists(NODE_ENV_FILE):
    with open(NODE_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()"""

        # Prepare db path code
        db_path_code = ""
        if "db_path_env" in service and "db_path" in service:
            db_path_code = f'if "{service["db_path_env"]}" not in os.environ:\n    os.environ["{service["db_path_env"]}"] = str(DATA_DIR / "{service["db_path"]}")'

        # Workers code
        workers_code = ""
        if "workers" in service:
            workers_code = f'    "--workers",\n    "{service["workers"]}",\n'

        # Extra uvicorn args
        extra_uvicorn_code = ""
        if service.get("extra_uvicorn_args"):
            args_code = ",\n".join(f'    "{arg}",' for arg in service["extra_uvicorn_args"])
            extra_uvicorn_code = args_code + ",\n"

        # Choose template
        if service.get("type") == "script":
            template = Template(SCRIPT_TEMPLATE)
        else:
            template = Template(UVICORN_TEMPLATE)

        # Prepare variables for template substitution
        vars = {
            "service_name": name,
            "PYTHONPATH": ":".join(["REPO_DIR"] + [f"REPO_DIR/{p}" for p in service.get("extra_paths", [])]),
            "module": service.get("module", ""),
            "script_path": service.get("script_path", ""),
            "bind_host_env": service.get("bind_host_env", ""),
            "bind_host_default": service.get("bind_host_default", "127.0.0.1"),
            "port_env": service.get("port_env", ""),
            "port_default": service.get("port_default", ""),
            "workers_code": workers_code,
            "extra_uvicorn_code": extra_uvicorn_code,
            "wallet_env_code": wallet_env_code,
            "load_node_env_code": load_node_env_code,
            "db_path_code": db_path_code,
            "service_name": name,
            "module": service.get("module", ""),
            "script_path": service.get("script_path", ""),
            "bind_host_env": service.get("bind_host_env", ""),
            "bind_host_default": service.get("bind_host_default", "127.0.0.1"),
            "port_env": service.get("port_env", ""),
            "port_default": service.get("port_default", ""),
        }

        if service.get("type") == "script":
            template = Template(SCRIPT_TEMPLATE)
        else:
            template = Template(UVICORN_TEMPLATE)

        content = template.safe_substitute(vars)

        output_path = Path("apps") / name / f"aitbc-{name}-wrapper.py"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        output_path.chmod(0o755)
        print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
