"""Minimal HIPAA enclave example for unit-test compatibility."""

from dataclasses import dataclass


@dataclass
class PHIRecord:
    patient_id: str
    data: dict[str, str]


class HIPAAEnclave:
    def __init__(self, enclave_id: str) -> None:
        self.enclave_id = enclave_id
        self._started = False

    def start(self) -> None:
        self._started = True

    def process(self, record: PHIRecord) -> dict[str, str]:
        result: dict[str, str] = {"patient_id": record.patient_id}
        for key in record.data:
            result[key] = "REDACTED"
        return result
