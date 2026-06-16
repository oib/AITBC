import sys

import aitbc

print("sys.path in test:")
for p in sys.path:
    print(f"  {p}")

print(f"aitbc location: {aitbc.__file__}")
