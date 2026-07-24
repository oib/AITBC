"""Compliance-aware sub-networks for sensitive edge workloads (v0.15.2 §B1).

ponytail: This is a routing-policy skeleton. Real sub-network segmentation
needs network-level isolation (VLANs, VPCs, eBPF) and attestation before
admission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework, DataClassification, normalize_classification


class WorkloadStatus(StrEnum):
    """Status of a workload assigned to a compliance subnet."""

    PENDING = "pending"
    ISOLATED = "isolated"
    RELEASED = "released"


@dataclass
class ComplianceSubnet:
    """A segmented sub-network that only accepts certain classifications."""

    subnet_id: str
    allowed_frameworks: set[ComplianceFramework] = field(default_factory=set)
    allowed_classifications: set[DataClassification] = field(default_factory=set)
    workloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: str = "active"

    def __post_init__(self) -> None:
        if not self.subnet_id:
            raise ValueError("subnet_id is required")
        self.allowed_classifications = {normalize_classification(c) for c in self.allowed_classifications}

    def allows(self, framework: ComplianceFramework, classification: DataClassification | str) -> bool:
        """Return True if the subnet accepts the framework and classification."""
        norm = normalize_classification(classification)
        if self.allowed_frameworks and framework not in self.allowed_frameworks:
            return False
        if self.allowed_classifications and norm not in self.allowed_classifications:
            return False
        return True

    def assign(
        self,
        workload_id: str,
        framework: ComplianceFramework,
        classification: DataClassification | str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assign a workload to the subnet after compliance checks."""
        if not self.allows(framework, classification):
            raise PolicyViolationError(f"subnet {self.subnet_id} does not accept {framework.value}/{classification}")
        record = {
            "workload_id": workload_id,
            "framework": framework.value,
            "classification": str(classification),
            "status": WorkloadStatus.ISOLATED.value,
            "meta": meta or {},
        }
        self.workloads[workload_id] = record
        return record

    def release(self, workload_id: str) -> None:
        """Release a workload from the subnet."""
        if workload_id in self.workloads:
            self.workloads[workload_id]["status"] = WorkloadStatus.RELEASED.value

    def is_isolated(self, workload_id: str) -> bool:
        """Return True if the workload is currently isolated in this subnet."""
        workload = self.workloads.get(workload_id)
        return workload is not None and workload["status"] == WorkloadStatus.ISOLATED.value


class SubnetRegistry:
    """Registry of compliance sub-networks."""

    def __init__(self) -> None:
        self._subnets: dict[str, ComplianceSubnet] = {}

    def register(self, subnet: ComplianceSubnet) -> None:
        """Register a subnet."""
        self._subnets[subnet.subnet_id] = subnet

    def assign(
        self,
        workload_id: str,
        framework: ComplianceFramework,
        classification: DataClassification | str,
        subnet_id: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route a workload to the named subnet."""
        subnet = self._subnets.get(subnet_id)
        if subnet is None:
            raise ValueError(f"subnet {subnet_id} not found")
        return subnet.assign(workload_id, framework, classification, meta)

    def is_isolated(self, subnet_id: str, workload_id: str) -> bool:
        """Return True if the workload is isolated in the named subnet."""
        subnet = self._subnets.get(subnet_id)
        return subnet is not None and subnet.is_isolated(workload_id)
