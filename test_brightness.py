"""Quick test: directly invoke the brightness skill."""
import sys
sys.path.insert(0, ".")

from skills import registry

print("=" * 50)
print("Testing set_brightness(50)")
print("=" * 50)
result = registry.execute("set_brightness", {"level": 50})
print(f"Result: {result}")
print("=" * 50)
