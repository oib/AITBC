#!/usr/bin/env python3
"""
Migrate hardcoded Environment variables to /etc/aitbc/%N.env for all services.

This script:
1. Identifies services with hardcoded Environment= lines
2. Moves them to EnvironmentFile=/etc/aitbc/%N.env
3. Creates .env template files for each service
4. Updates User= from root to aitbc-internal where appropriate
"""

import re
from pathlib import Path


def migrate_service_file(service_file: Path) -> dict[str, any]:
    """Migrate a single service file to use EnvironmentFile."""
    content = service_file.read_text()
    lines = content.split("\n")

    result = {
        "file": str(service_file),
        "service_name": service_file.stem,
        "has_hardcoded_env": False,
        "env_vars": [],
        "uses_env_file": False,
        "user": None,
        "changes": [],
    }

    # Extract service name for env file
    service_name = service_file.stem.replace(".service", "")

    # Find User= line
    for i, line in enumerate(lines):
        if line.startswith("User="):
            result["user"] = line.split("=")[1].strip()
            if result["user"] == "root":
                result["changes"].append(f"User=aitbc-internal (was {result['user']})")
                lines[i] = "User=aitbc-internal"

    # Find Environment= lines (not EnvironmentFile)
    env_lines = []
    env_file_lines = []
    for i, line in enumerate(lines):
        if line.startswith("Environment=") and "EnvironmentFile" not in line:
            result["has_hardcoded_env"] = True
            # Extract variable name and value
            match = re.match(r'Environment="?([^=]+)=([^"]+)"?', line)
            if match:
                var_name, var_value = match.groups()
                result["env_vars"].append((var_name, var_value))
                env_lines.append((i, line))
        elif line.startswith("EnvironmentFile"):
            result["uses_env_file"] = True
            env_file_lines.append(line)

    # If there are hardcoded env vars, add EnvironmentFile
    if env_lines:
        # Remove hardcoded Environment= lines
        for i, _ in env_lines:
            lines[i] = f"# Environment={lines[i].split('=', 1)[1]} # Moved to /etc/aitbc/{service_name}.env"

        # Add EnvironmentFile after EnvironmentFile lines or after User
        insert_pos = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("EnvironmentFile"):
                insert_pos = i + 1
                break
            elif line.startswith("User="):
                insert_pos = i + 1
                break

        # Add EnvironmentFile line
        env_file_line = f"EnvironmentFile=/etc/aitbc/{service_name}.env"
        lines.insert(insert_pos, env_file_line)
        result["changes"].append(f"Added {env_file_line}")

    # Write back
    new_content = "\n".join(lines)
    service_file.write_text(new_content)

    return result


def create_env_template(service_name: str, env_vars: list[tuple[str, str]]) -> str:
    """Create an .env template file content."""
    lines = [
        f"# Environment file for {service_name}",
        "# Created by v0.5.0 systemd hardening",
        "#",
        "# TODO: Replace placeholder values with actual production values",
        "#",
    ]

    for var_name, var_value in env_vars:
        # Check if value looks like a secret
        if any(keyword in var_name.lower() for keyword in ["password", "secret", "token", "key", "auth"]):
            lines.append(f"{var_name}=REPLACE_WITH_SECRET")
        else:
            lines.append(f"{var_name}={var_value}")

    return "\n".join(lines)


def main() -> int:
    """Main migration function."""
    services_dir = Path("/opt/aitbc/apps")
    service_files = list(services_dir.rglob("*.service"))

    print("=" * 60)
    print("Migrating Environment variables to /etc/aitbc/%N.env")
    print("=" * 60)
    print()

    results = []
    for service_file in service_files:
        result = migrate_service_file(service_file)
        if result["changes"]:
            results.append(result)

    # Print summary
    print(f"Processed {len(service_files)} service files")
    print(f"Modified {len(results)} files")
    print()

    # Create .env templates
    templates_dir = Path("/opt/aitbc/templates/env")
    templates_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        if result["env_vars"]:
            template_content = create_env_template(result["service_name"], result["env_vars"])
            template_file = templates_dir / f"{result['service_name']}.env"
            template_file.write_text(template_content)
            print(f"Created template: {template_file}")

    print()
    print("=" * 60)
    print("Migration Complete")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review /opt/aitbc/templates/env/*.env files")
    print("2. Replace placeholder values with actual production secrets")
    print("3. Copy templates to /etc/aitbc/ during deployment")
    print("4. Restart services to apply changes")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
