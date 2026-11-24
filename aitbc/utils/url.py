"""URL construction helpers."""

from urllib.parse import quote


def quote_path_segment(value: str) -> str:
    """Percent-encode a value for interpolation as ONE URL path segment.

    ``quote(value, safe="")`` alone still leaves ``.`` untouched, so a value
    of ``..`` would survive as a dot-segment and let httpx normalise
    ``/rpc/escrow/..`` up to ``/rpc/`` — a path escape even with every other
    character encoded. Encoding dots as ``%2E`` keeps the value a single
    literal segment; upstream frameworks percent-decode it back to the
    original string inside the path parameter.
    """
    return quote(str(value), safe="").replace(".", "%2E")
