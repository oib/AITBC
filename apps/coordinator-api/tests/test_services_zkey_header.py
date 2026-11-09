"""Coverage for zkey_header parser (#1289 residual).

Pure binary parser for snarkjs .zkey/.r1cs containers — the guard that
keeps proving keys bound to the right circuit shape (V23-26a/V23-91
class). Tests build synthetic containers; no circuit artifacts needed.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from coordinator_api.contexts.zk_applications.services.zkey_header import (
    ZKeyFormatError,
    read_r1cs_header,
    read_zkey_contribution_count,
    read_zkey_header,
)


def _container(magic: bytes, sections: list[tuple[int, bytes]]) -> bytes:
    out = magic + struct.pack("<II", 1, len(sections))
    for sid, payload in sections:
        out += struct.pack("<IQ", sid, len(payload)) + payload
    return out


def _zkey_body(n_vars: int, n_public: int, domain_size: int, n8q: int = 2, n8r: int = 3) -> bytes:
    body = struct.pack("<I", n8q) + b"Q" * n8q
    body += struct.pack("<I", n8r) + b"R" * n8r
    body += struct.pack("<III", n_vars, n_public, domain_size)
    return body


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _zkey_file(tmp_path: Path, **kw) -> Path:
    body = _zkey_body(kw.get("n_vars", 100), kw.get("n_public", 2), kw.get("domain_size", 128))
    sections = [(1, struct.pack("<I", kw.get("protocol", 1))), (2, body)]
    if "contributions" in kw:
        sections.append((10, b"H" * 64 + struct.pack("<I", kw["contributions"])))
    return _write(tmp_path, "circuit.zkey", _container(b"zkey", sections))


def _r1cs_file(tmp_path: Path, n_wires: int = 50, n_pub_out: int = 1, n_pub_in: int = 1, n_constraints: int = 40) -> Path:
    body = struct.pack("<I", 4) + b"F" * 4
    body += struct.pack("<IIII", n_wires, n_pub_out, n_pub_in, 7)
    body += struct.pack("<Q", 1000)  # nLabels uint64
    body += struct.pack("<I", n_constraints)
    return _write(tmp_path, "circuit.r1cs", _container(b"r1cs", [(1, body)]))


# ---------------------------------------------------------------------------
# zkey header
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_zkey_header_parses_shape(tmp_path):
    h = read_zkey_header(_zkey_file(tmp_path, n_vars=100, n_public=2, domain_size=128))
    assert h.protocol == 1
    assert h.is_groth16
    assert (h.n_vars, h.n_public, h.domain_size) == (100, 2, 128)


@pytest.mark.unit
def test_zkey_header_variable_field_widths(tmp_path):
    # n8q/n8r are variable-width byte counts that must be stepped over,
    # not assumed — different widths must still parse correctly.
    h = read_zkey_header(_zkey_file(tmp_path, n_vars=7, n_public=3, domain_size=16, n8q=0, n8r=9))
    assert (h.n_vars, h.n_public, h.domain_size) == (7, 3, 16)


@pytest.mark.unit
def test_zkey_header_non_groth16(tmp_path):
    h = read_zkey_header(_zkey_file(tmp_path, protocol=2))
    assert h.protocol == 2
    assert not h.is_groth16


@pytest.mark.unit
def test_zkey_header_wrong_magic(tmp_path):
    p = _write(tmp_path, "bad.zkey", _container(b"r1cs", [(1, b"x")]))
    with pytest.raises(ZKeyFormatError, match="magic"):
        read_zkey_header(p)


@pytest.mark.unit
def test_zkey_header_truncated_section_table(tmp_path):
    p = _write(tmp_path, "trunc.zkey", b"zkey" + struct.pack("<II", 1, 5) + b"short")
    with pytest.raises(ZKeyFormatError, match="truncated"):
        read_zkey_header(p)


@pytest.mark.unit
def test_zkey_header_missing_sections(tmp_path):
    p = _write(tmp_path, "nosec.zkey", _container(b"zkey", [(3, b"payload")]))
    with pytest.raises(ZKeyFormatError, match="missing header sections"):
        read_zkey_header(p)


@pytest.mark.unit
def test_zkey_header_seeks_past_unwanted_sections(tmp_path):
    # A large unwanted section before the wanted ones must not break parsing.
    big = b"X" * 4096
    sections = [(9, big), (1, struct.pack("<I", 1)), (2, _zkey_body(11, 1, 32))]
    p = _write(tmp_path, "big.zkey", _container(b"zkey", sections))
    h = read_zkey_header(p)
    assert (h.n_vars, h.n_public) == (11, 1)


# ---------------------------------------------------------------------------
# contribution count
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_contribution_count(tmp_path):
    p = _zkey_file(tmp_path, contributions=7)
    assert read_zkey_contribution_count(p) == 7


@pytest.mark.unit
def test_contribution_count_missing_section(tmp_path):
    p = _zkey_file(tmp_path)  # no section 10
    with pytest.raises(ZKeyFormatError, match="no MPC parameters"):
        read_zkey_contribution_count(p)


@pytest.mark.unit
def test_contribution_count_short_body(tmp_path):
    sections = [(10, b"short")]
    p = _write(tmp_path, "short.zkey", _container(b"zkey", sections))
    with pytest.raises(ZKeyFormatError, match="too short"):
        read_zkey_contribution_count(p)


# ---------------------------------------------------------------------------
# r1cs header
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_r1cs_header_parses(tmp_path):
    h = read_r1cs_header(_r1cs_file(tmp_path, n_wires=50, n_pub_out=1, n_pub_in=2, n_constraints=40))
    assert h.n_wires == 50
    assert h.n_public == 3  # public outputs + public inputs
    assert h.n_constraints == 40


@pytest.mark.unit
def test_r1cs_header_missing_section(tmp_path):
    p = _write(tmp_path, "empty.r1cs", _container(b"r1cs", []))
    with pytest.raises(ZKeyFormatError, match="missing header"):
        read_r1cs_header(p)
