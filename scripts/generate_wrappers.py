#!/usr/bin/env python3
"""
Generate service wrapper scripts from template.
Usage: python scripts/generate_wrappers.py
"""

from pathlib import Path

UVICORN_TEMPLATE = (
    "#!/usr/bin/env python3\n"
    '"""\n'
    "Wrapper script for {service_name} service\n"
    "Uses centralized aitbc utilities for path configuration\n"
    '"""\n\n'
    "import os\n"
    "from pathlib import Path\n"
    "from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR, KEYSTORE_DIR\n\n"
    "# Set up environment using aitbc constants\n"
    'os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)\n'
    'os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)\n'
    'os.environ["PYTHONPATH"] = "{PYTHONPATH}"\n'
    'os.environ["DATA_DIR"] = str(DATA_DIR)\n'
    'os.environ["LOG_DIR"] = str(LOG_DIR)\n\n'
    "{wallet_env_code}\n\n"
    "{load_node_env_code}\n\n"
    "{db_path_code}\n\n"
    'log_level = os.getenv("LOG_LEVEL", "info").lower()\n'
    'access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")\n\n'
    "# {service_name} bind configuration\n"
    "# Use {bind_host_env} for bind address (default: {bind_host_default})\n"
    "# Use {port_env} for port (default: {port_default})\n"
    'bind_host = os.getenv("{bind_host_env}", "{bind_host_default}")\n'
    'bind_port = os.getenv("{port_env}", "{port_default}")\n\n'
    "# Execute the actual service\n"
    "exec_cmd = [\n"
    '    "/opt/aitbc/venv/bin/python",\n'
    '    "-m",\n'
    '    "uvicorn",\n'
    '    "{module}",\n'
    '    "--host",\n'
    "    bind_host,\n"
    '    "--port",\n'
    "    bind_port,\n"
    "{workers_code}{extra_uvicorn_code}"
    '    "--log-level",\n'
    "    log_level,\n"
    "]\n"
    "if access_log:\n"
    '    exec_cmd.append("--access-log")\n'
    "os.execvp(exec_cmd[0], exec_cmd)\n"
)

SCRIPT_TEMPLATE = (
    "#!/usr/bin/env python3\n"
    '"""\n'
    "Wrapper script for {service_name} service\n"
    "Uses centralized aitbc utilities for path configuration\n"
    '"""\n\n'
    "import os\n"
    "from pathlib import Path\n"
    "from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR, KEYSTORE_DIR\n\n"
    "# Set up environment using aitbc constants\n"
    'os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)\n'
    'os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)\n'
    'os.environ["PYTHONPATH"] = "{PYTHONPATH}"\n'
    'os.environ["DATA_DIR"] = str(DATA_DIR)\n'
    'os.environ["LOG_DIR"] = str(LOG_DIR)\n\n'
    "{load_node_env_code}\n\n"
    'log_level = os.getenv("LOG_LEVEL", "info").lower()\n'
    'access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")\n\n'
    "# Execute the actual service\n"
    "exec_cmd = [\n"
    '    "/opt/aitbc/venv/bin/python",\n'
    '    "{script_path}",\n'
    "]\n"
    "os.execvp(exec_cmd[0], exec_cmd)\n"
)


def main():
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
            "workers": "",
            "extra_uvicorn_args": [],
            "wallet_dir_env": "",
            "load_node_env": False,
            "db_path": "",
            "db_path_env": "",
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
            "wallet_dir_env": "",
            "load_node_env": False,
            "db_path": "",
            "db_path_env": "",
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
            "load_node_env": False,
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
            "load_node_env": False,
            "db_path": "",
            "db_path_env": "",
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
            "workers": "",
            "extra_uvicorn_args": [],
            "load_node_env": False,
            "db_path": "",
            "db_path_env": "",
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
    ]

    for service in SERVICES:
        name = service["name"]

        pythonpath = ":".join(["REPO_DIR"] + ["REPO_DIR/" + p for p in service.get("extra_paths", [])])

        if service.get("wallet_dir_env"):
            f'wallet_dir = os.getenv("{service["wallet_dir_env"]}")\nif wallet_dir:\n    os.environ["WALLET_DIR"] = wallet_dir'

        if service.get("load_node_env"):
            pass

        if service.get("db_path_env") and service.get("db_path"):
            f'if "{service["db_path_env"]}" not in os.environ:\n    os.environ["{service["db_path_env"]}"] = str(DATA_DIR / "{service["db_path"]}")'

        if service.get("workers"):
            '    "--workers",\n    "{}",\n'.format(service["workers"])

        if service.get("extra_uvicorn_args"):
            ",\n".join(f'    "{arg}"' for arg in service["extra_uvicorn_args"]) + ",\n"

        pythonpath = ":".join(["REPO_DIR"] + ["REPO_DIR/" + p for p in service.get("extra_paths", [])])

        vars = {
            "service_name": service["name"],
            "PYTHONPATH": pythonpath,
            "module": service.get("module", ""),
            "script_path": service.get("script_path", ""),
            "bind_host_env": service.get("bind_host_env", ""),
            "bind_host_default": service.get("bind_host_default", "127.0.0.1"),
            "port_env": service.get("port_env", ""),
            "port_default": service.get("port_default", ""),
            "workers_code": '    "--workers",\n    "{}",\n'.format(service["workers"]) if service.get("workers") else "",
            "extra_uvicorn_code": ",\n".join(f'    "{arg}"' for arg in service["extra_uvicorn_args"]) + ",\n"
            if service.get("extra_uvicorn_args")
            else "",
            "wallet_env_code": f'wallet_dir = os.getenv("{service["wallet_dir_env"]}")\nif wallet_dir:\n    os.environ["WALLET_DIR"] = wallet_dir'
            if service.get("wallet_dir_env")
            else "",
            "load_node_env_code": (
                "# Load node.env to get additional config\n"
                "if os.path.exists(NODE_ENV_FILE):\n"
                "    with open(NODE_ENV_FILE) as f:\n"
                "        for line in f:\n"
                "            line = line.strip()\n"
                '            if line and not line.startswith("#") and "=" in line:\n'
                '                key, value = line.split("=", 1)\n'
                "                os.environ[key.strip()] = value.strip()"
            )
            if service.get("load_node_env")
            else "",
            "db_path_code": f'if "{service.get("db_path_env", "")}" not in os.environ:\n    os.environ["{service.get("db_path_env", "")}"] = str(DATA_DIR / "{service.get("db_path", "")}")'
            if service.get("db_path_env") and service.get("db_path")
            else "",
        }

        if service.get("type") == "script":
            content = SCRIPT_TEMPLATE.format(**vars)
        else:
            content = UVICORN_TEMPLATE.format(**vars)

        output_path = Path("apps") / name / f"aitbc-{name}-wrapper.py"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        output_path.chmod(0o755)
        print("Generated " + str(output_path))


if __name__ == "__main__":
    main()
