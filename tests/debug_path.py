import sys

print("sys.path in test:")
for p in sys.path:
    print(f"  {p}")
import aitbc  # noqa: E402

print(f"aitbc location: {aitbc.__file__}")
