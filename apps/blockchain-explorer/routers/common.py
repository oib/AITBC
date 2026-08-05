"""Common helpers for blockchain-explorer routers."""

_LIKE_ESCAPE_CHAR = "|"


def like_pattern(raw: str) -> str:
    """Build a SQLite LIKE pattern that treats ``%`` and ``_`` as literals.

    The escape character is ``|``. Search strings containing ``|`` itself are
    doubled so they remain literal.
    """
    escaped = raw.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
    escaped = escaped.replace("%", f"{_LIKE_ESCAPE_CHAR}%")
    escaped = escaped.replace("_", f"{_LIKE_ESCAPE_CHAR}_")
    return f"%{escaped}%"


_CSV_FORMULA_CHARS = frozenset({"=", "-", "+", "@", "\t", "\r"})


def sanitize_csv_value(value: str) -> str:
    """Prefix a CSV cell with a single quote to neutralize formula injection.

    Spreadsheet applications interpret cells starting with ``=``, ``-``, ``+``,
    ``@``, tab or carriage-return as formulas or control characters. A leading
    single quote forces them to be treated as text.
    """
    value = str(value)
    if value and value[0] in _CSV_FORMULA_CHARS:
        return f"' {value}"
    return value
