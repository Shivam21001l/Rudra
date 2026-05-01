import sys
import ollama

sys.stdout.reconfigure(encoding='utf-8')

def test_ollama():
    try:
        print("calling ollama with num_predict 4096...")
        stream = ollama.chat(
            model="qwen3:1.7b",
            messages=[{"role": "user", "content": "hello"}],
            options={"num_predict": 4096, "temperature": 0.3, "top_k": 20},
            stream=True
        )
        for chunk in stream:
            print(chunk["message"]["content"], end="", flush=True)
        print("\ndone!")
    except Exception as e:
        print("error:", e)

if __name__ == "__main__":
    test_ollama()
