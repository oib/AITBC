#!/usr/bin/env python3
"""
Prerequisite Check Generator

Generates prerequisite validation checks for training stages.
Validates that all dependencies (stage and resource) are satisfied before running a stage.
"""

import json
import sys
from pathlib import Path

STAGE_ORDER = [
    "stage0_environment_setup",
    "stage1_foundation",
    "stage2_operations_mastery",
    "stage3_ai_operations",
    "stage4_marketplace_economics",
    "stage5_expert_operations",
    "stage6_agent_identity_sdk",
    "stage7_cross_node_training",
    "stage8_advanced_agent_specialization",
    "stage9_multi_chain_architecture",
]


class PrerequisiteChecker:
    def __init__(self, stages_dir: Path):
        self.stages_dir = stages_dir
        self.stages: dict[str, dict] = {}
        self.errors = []
        self.warnings = []

    def load_stages(self):
        """Load all stage JSON files."""
        for stage_name in STAGE_ORDER:
            stage_file = self.stages_dir / f"{stage_name}.json"
            if stage_file.exists():
                self.stages[stage_name] = json.loads(stage_file.read_text())
            else:
                self.warnings.append(f"Stage file not found: {stage_file}")

    def check_stage_order(self, stage_name: str) -> bool:
        """Check that depends_on stages come before this stage in order."""
        stage_data = self.stages.get(stage_name)
        if not stage_data:
            return False

        depends_on = stage_data.get("depends_on", [])
        stage_index = STAGE_ORDER.index(stage_name)

        for dep_stage in depends_on:
            if dep_stage not in STAGE_ORDER:
                self.errors.append(f"{stage_name}: depends_on references unknown stage '{dep_stage}'")
                continue

            dep_index = STAGE_ORDER.index(dep_stage)
            if dep_index >= stage_index:
                self.errors.append(
                    f"{stage_name}: depends_on '{dep_stage}' comes after it in stage order "
                    f"(index {dep_index} >= {stage_index})"
                )

        return len(self.errors) == 0

    def check_resource_dependencies(self, stage_name: str) -> bool:
        """Check that resource_depends references valid stages."""
        stage_data = self.stages.get(stage_name)
        if not stage_data:
            return False

        resource_depends = stage_data.get("resource_depends", [])
        depends_on = stage_data.get("depends_on", [])

        for resource_dep in resource_depends:
            provider_stage = resource_dep.get("stage")
            if provider_stage:
                if provider_stage not in STAGE_ORDER:
                    self.errors.append(
                        f"{stage_name}: resource_depends references unknown stage '{provider_stage}'"
                    )
                elif provider_stage not in depends_on and provider_stage != stage_name:
                    self.warnings.append(
                        f"{stage_name}: resource_depends stage '{provider_stage}' "
                        f"not in depends_on (should be added)"
                    )

        return len(self.errors) == 0

    def check_wallet_balance_placement(self, stage_name: str) -> bool:
        """Check that wallet_balance appears before operations with wallet+password."""
        stage_data = self.stages.get(stage_name)
        if not stage_data:
            return False

        operations = stage_data.get("training_data", {}).get("operations", [])
        wallet_balance_found = False

        for i, op in enumerate(operations):
            op_name = op.get("operation", "")
            params = op.get("parameters", {})

            if op_name == "wallet_balance":
                wallet_balance_found = True
                continue

            has_wallet = "wallet" in params
            has_password = "password" in params

            if has_wallet and has_password and not wallet_balance_found:
                self.errors.append(
                    f"{stage_name}: operation '{op_name}' (index {i}) has wallet+password "
                    f"but no wallet_balance check before it"
                )

        return len(self.errors) == 0

    def check_currency_fields(self, stage_name: str) -> bool:
        """Check that operations with amount/price have currency field."""
        stage_data = self.stages.get(stage_name)
        if not stage_data:
            return False

        operations = stage_data.get("training_data", {}).get("operations", [])
        currency_required_params = {"amount", "price", "bounty_amount", "stake_amount", "spread"}

        for i, op in enumerate(operations):
            op_name = op.get("operation", "")
            params = op.get("parameters", {})

            requires_currency = any(param in currency_required_params for param in params.keys())
            if requires_currency and "currency" not in params:
                self.errors.append(
                    f"{stage_name}: operation '{op_name}' (index {i}) has "
                    f"{currency_required_params} parameter(s) but missing 'currency' field"
                )

        return len(self.errors) == 0

    def validate_stage(self, stage_name: str) -> bool:
        """Run all prerequisite checks for a stage."""
        self.check_stage_order(stage_name)
        self.check_resource_dependencies(stage_name)
        self.check_wallet_balance_placement(stage_name)
        self.check_currency_fields(stage_name)
        return len(self.errors) == 0

    def validate_all(self) -> bool:
        """Validate all stages."""
        for stage_name in STAGE_ORDER:
            if stage_name in self.stages:
                self.validate_stage(stage_name)
        return len(self.errors) == 0

    def generate_prerequisite_script(self, stage_name: str) -> str:
        """Generate a bash script to check prerequisites for a stage."""
        stage_data = self.stages.get(stage_name)
        if not stage_data:
            return f"# Stage {stage_name} not found"

        depends_on = stage_data.get("depends_on", [])
        resource_depends = stage_data.get("resource_depends", [])

        script_lines = [
            "#!/bin/bash",
            f"# Prerequisite checks for {stage_name}",
            "#",
            "# This script validates that all prerequisites are satisfied",
            "# before starting the training stage.",
            "",
            "set -e",
            "",
            f'echo "Checking prerequisites for {stage_name}..."',
        ]

        # Check stage dependencies
        if depends_on:
            script_lines.append("# Stage dependencies")
            for dep_stage in depends_on:
                script_lines.extend([
                    f"if [ ! -f \"$(dirname \"$0\")/{dep_stage}.json\" ]; then",
                    f'  echo "❌ Missing prerequisite stage: {dep_stage}"',
                    "  exit 1",
                    "fi",
                    f'echo "✅ Prerequisite stage found: {dep_stage}"',
                    "",
                ])

        # Check resource dependencies
        if resource_depends:
            script_lines.append("# Resource dependencies")
            for res_dep in resource_depends:
                resource_type = res_dep.get("resource", "")
                condition = res_dep.get("condition", "")
                script_lines.extend([
                    f"# Check {resource_type}: {condition}",
                    f"# TODO: Implement resource check for {resource_type}",
                    f'echo "⚠️  Resource check not implemented: {resource_type}"',
                    "",
                ])

        script_lines.extend([
            f'echo "✅ All prerequisites satisfied for {stage_name}"',
            "exit 0",
        ])

        return "\n".join(script_lines)

    def report(self):
        """Print validation report."""
        print("Prerequisite Validation Report")
        print("=" * 50)

        if self.errors:
            print(f"❌ {len(self.errors)} error(s) found:")
            for error in self.errors:
                print(f"   - {error}")
        else:
            print("✅ No errors found")

        if self.warnings:
            print(f"\n⚠️  {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                print(f"   - {warning}")

        print("\nStage Status:")
        for stage_name in STAGE_ORDER:
            if stage_name in self.stages:
                print(f"   ✅ {stage_name}")
            else:
                print(f"   ❌ {stage_name} (file not found)")


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_prerequisite_checks.py <stages_dir> [stage_name]")
        print("  stages_dir: Path to directory containing stage JSON files")
        print("  stage_name: (optional) Generate prerequisite script for specific stage")
        sys.exit(1)

    stages_dir = Path(sys.argv[1])
    if not stages_dir.exists():
        print(f"❌ Stages directory not found: {stages_dir}")
        sys.exit(1)

    checker = PrerequisiteChecker(stages_dir)
    checker.load_stages()

    # If specific stage requested, generate prerequisite script
    if len(sys.argv) >= 3:
        stage_name = sys.argv[2]
        script = checker.generate_prerequisite_script(stage_name)
        print(script)
        sys.exit(0)

    # Otherwise, validate all stages
    checker.validate_all()
    checker.report()

    sys.exit(0 if len(checker.errors) == 0 else 1)


if __name__ == "__main__":
    main()
