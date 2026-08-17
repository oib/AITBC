"""Read the headers of snarkjs ``.zkey`` and ``.r1cs`` files.

Groth16 binds a proving key to one specific constraint system, and a verification key to
one specific proving key. Nothing about the filenames enforces that. ``receipt_simple``
carried a proving key for a 0-public-signal circuit next to a verification key for a
1-public-signal one (V23-26a), and the mismatch was invisible because both files existed
and were named plausibly.

Both formats share a container: a 4-byte magic, ``uint32`` version, ``uint32`` section
count, then ``(uint32 id, uint64 length, bytes payload)`` per section. Only the first
sections are read, by seeking — a proving key can be tens of megabytes and none of that is
needed to answer the question.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_GROTH16 = 1


class ZKeyFormatError(ValueError):
    """A file did not parse as the snarkjs binary format it was expected to be."""


def _read_sections(fh: BinaryIO, magic: bytes, wanted: set[int]) -> dict[int, bytes]:
    """Return the payloads of ``wanted`` sections, seeking past everything else."""
    header = fh.read(12)
    if len(header) < 12 or header[:4] != magic:
        raise ZKeyFormatError(f"expected magic {magic!r}, got {header[:4]!r}")

    (n_sections,) = struct.unpack("<I", header[8:12])
    found: dict[int, bytes] = {}
    for _ in range(n_sections):
        entry = fh.read(12)
        if len(entry) < 12:
            raise ZKeyFormatError("truncated section table")
        section_id, length = struct.unpack("<IQ", entry)
        # First occurrence wins: snarkjs permits repeated ids, and the header sections
        # this reads are written once.
        if section_id in wanted and section_id not in found:
            found[section_id] = fh.read(length)
        else:
            fh.seek(length, 1)
    return found


@dataclass(frozen=True)
class ZKeyHeader:
    """The shape of the circuit a proving key was generated for."""

    protocol: int
    n_vars: int
    n_public: int
    domain_size: int

    @property
    def is_groth16(self) -> bool:
        return self.protocol == _GROTH16


@dataclass(frozen=True)
class R1CSHeader:
    """The shape of a compiled constraint system."""

    n_wires: int
    n_public: int
    n_constraints: int


def read_zkey_header(path: Path) -> ZKeyHeader:
    """Read protocol and circuit shape from a ``.zkey``."""
    with path.open("rb") as fh:
        sections = _read_sections(fh, b"zkey", {1, 2})

    if 1 not in sections or 2 not in sections:
        raise ZKeyFormatError(f"{path.name}: missing header sections")

    (protocol,) = struct.unpack("<I", sections[1][:4])
    body = sections[2]

    # The two field sizes are variable-width and precede the counts, so they must be
    # stepped over rather than assumed: n8q, q, n8r, r, then nVars, nPublic, domainSize.
    (n8q,) = struct.unpack("<I", body[:4])
    offset = 4 + n8q
    (n8r,) = struct.unpack("<I", body[offset : offset + 4])
    offset += 4 + n8r
    n_vars, n_public, domain_size = struct.unpack("<III", body[offset : offset + 12])

    return ZKeyHeader(protocol=protocol, n_vars=n_vars, n_public=n_public, domain_size=domain_size)


def read_zkey_contribution_count(path: Path) -> int:
    """Return how many phase-2 contributions a ``.zkey`` actually carries.

    The ``_0000``/``_0001`` suffix is a filename convention, and V23-24's refusal to load a
    zero-contribution key was written against that convention. Renaming the file walks past
    it: ``modular_ml_components_0001.zkey`` was a key straight out of ``groth16 setup``,
    carrying no contribution at all, and it was accepted for three releases because its name
    ended in ``_0001`` (V23-91).

    Section 10 is snarkjs's MPC parameters: a 64-byte constraint-system hash followed by a
    ``uint32`` count and then one record per contribution. The count is the artifact's own
    statement about itself, so it is what the guard should read.
    """
    with path.open("rb") as fh:
        sections = _read_sections(fh, b"zkey", {10})

    if 10 not in sections:
        raise ZKeyFormatError(f"{path.name}: no MPC parameters section, so contributions cannot be counted")

    body = sections[10]
    if len(body) < 68:
        raise ZKeyFormatError(f"{path.name}: MPC parameters section is {len(body)} bytes, too short to hold a count")

    (count,) = struct.unpack("<I", body[64:68])
    return int(count)


def read_r1cs_header(path: Path) -> R1CSHeader:
    """Read circuit shape from a compiled ``.r1cs``."""
    with path.open("rb") as fh:
        sections = _read_sections(fh, b"r1cs", {1})

    if 1 not in sections:
        raise ZKeyFormatError(f"{path.name}: missing header section")

    body = sections[1]
    (n8,) = struct.unpack("<I", body[:4])
    offset = 4 + n8
    n_wires, n_pub_out, n_pub_in, _n_prv_in = struct.unpack("<IIII", body[offset : offset + 16])
    offset += 16 + 8  # nLabels is uint64
    (n_constraints,) = struct.unpack("<I", body[offset : offset + 4])

    # A zkey's nPublic counts public outputs and public inputs together.
    return R1CSHeader(n_wires=n_wires, n_public=n_pub_out + n_pub_in, n_constraints=n_constraints)
