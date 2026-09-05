# aitbc-errors

The AITBC exception hierarchy, in a leaf package with **no dependencies**.

It exists so that importing an exception class costs nothing. The hierarchy
previously lived only in the repo-root `aitbc.exceptions` module. That module
is itself dependency-free, but reaching it requires executing
`aitbc/__init__.py`, which imports `aitbc.middleware` and so pulls in fastapi,
sqlalchemy and prometheus_client. A library that wanted one exception class
had to install a web stack to get it.

`aitbc.exceptions` now re-exports from here, so the classes are the *same
objects*: existing `except aitbc.exceptions.NetworkError` handlers are
unaffected.

Import from whichever name suits the layer:

```python
from aitbc_errors import NetworkError      # leaf packages, SDKs
from aitbc.exceptions import NetworkError  # application code, unchanged
```

Do not add dependencies to this package.
