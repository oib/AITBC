"""Unit tests for the local hardware probe used by `aitbc energy suggest`."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from aitbc_cli.utils.hardware_probe import probe_cpu_model, probe_gpus

NVIDIA_SMI_OUT = "0, NVIDIA GeForce RTX 4060 Ti, 16380, 165.00, GPU-deadbeef-1234\n"


def _ok(stdout: str) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def test_probe_gpus_parses_csv():
    with patch("subprocess.run", return_value=_ok(NVIDIA_SMI_OUT)):
        gpus = probe_gpus()
    assert len(gpus) == 1
    g = gpus[0]
    assert g.index == 0
    assert g.name == "NVIDIA GeForce RTX 4060 Ti"
    assert g.memory_gb == 15  # 16380 MiB -> 15 GiB
    assert g.power_limit_w == 165
    assert g.uuid == "GPU-deadbeef-1234"


def test_probe_gpus_multi():
    out = NVIDIA_SMI_OUT + "1, NVIDIA GeForce RTX 4090, 24564, 450.00, GPU-cafe-5678\n"
    with patch("subprocess.run", return_value=_ok(out)):
        gpus = probe_gpus()
    assert [g.index for g in gpus] == [0, 1]
    assert gpus[1].power_limit_w == 450


def test_probe_gpus_missing_binary():
    with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")):
        assert probe_gpus() == []


def test_probe_gpus_failure_rc():
    m = _ok("")
    m.returncode = 9
    m.stderr = "no devices"
    with patch("subprocess.run", return_value=m):
        assert probe_gpus() == []


def test_probe_gpus_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 10)):
        assert probe_gpus() == []


def test_probe_cpu_model():
    lscpu = "Architecture:            x86_64\nModel name:              AMD Ryzen 9 5950X 16-Core Processor\nCPU(s):                  32\n"
    with patch("subprocess.run", return_value=_ok(lscpu)):
        assert probe_cpu_model() == "AMD Ryzen 9 5950X 16-Core Processor"


def test_probe_cpu_model_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError("lscpu")):
        assert probe_cpu_model() is None
