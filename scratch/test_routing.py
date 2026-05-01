import sys
sys.path.append('.')
from brain import classify_task

test_cases = [
    ("How are you?", "agent"),
    ("What is Python?", "agent"),
    ("Write a python script to list files", "code"),
    ("Fix this error: SyntaxError: invalid syntax", "code"),
    ("Tell me a joke about programmers", "agent"),
    ("Explain the concept of recursion", "agent"), # Heuristic: if it's just "explain", maybe agent? 
    ("implement a quicksort in C++", "code"),
    ("how to use powershell to list services", "code"),
]

print("Testing Routing Logic:")
for text, expected in test_cases:
    result = classify_task(text)
    status = "[OK]" if result == expected else "[FAIL]"
    print(f"  {status} Input: '{text}' -> Got: {result} (Expected: {expected})")
