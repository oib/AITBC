"""Phase-0 test for P2P-PAYLOAD-DECOMPRESSION-BOMB-1 (#798).

``decode_payload`` gunzips unauthenticated input with no output limit:
a ~65 KB line (the asyncio readline cap) expands to ~48 MiB and the decoded
result is returned before callers even check the message type
(p2p_network._handle_inbound_connection, _listen_to_stream, chain_sync
gossip). Parallel connections multiply the memory.

Desired behaviour (pinned here): a ``GZ:`` payload whose decompressed size
exceeds the configured cap is REFUSED (raises), while legitimate payloads
still decode. The over-cap case FAILS on current main — decode_payload
happily returns the expanded object — that is the bug demonstration.
"""

import base64
import gzip

import pytest
from aitbc_chain.network.compression import COMPRESSION_PREFIX, decode_payload, encode_payload


def _gz_line(raw: bytes) -> str:
    return COMPRESSION_PREFIX + base64.b64encode(gzip.compress(raw)).decode("ascii")


class TestDecompressionCap:
    def test_over_cap_payload_is_refused(self):
        """48 MiB of compressible content must not decode to an object.

        On current main this returns the expanded dict instead of raising —
        the bug. Desired: a bounded reader raises before materialising the
        full output.
        """
        big = b'{"data": "' + b"0" * (48 * 1024 * 1024) + b'"}'
        line = _gz_line(big)
        assert len(line) < 70_000  # still one readline-sized inbound line
        with pytest.raises(ValueError):
            decode_payload(line)

    def test_legit_compressed_payload_still_decodes(self):
        msg = {"type": "handshake", "node_id": "n1", "height": 42}
        assert decode_payload(encode_payload(msg)) == msg

    def test_small_gz_payload_decodes(self):
        line = _gz_line(b'{"type": "ping"}')
        assert decode_payload(line) == {"type": "ping"}

    def test_plain_json_fallback_unchanged(self):
        assert decode_payload('{"type": "ping"}') == {"type": "ping"}
