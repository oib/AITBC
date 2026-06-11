import sys

print("sys.path in test:")
for p in sys.path:
    print(f"  {p}")
import aitbc

print(f"aitbc location: {aitbc.__file__}")