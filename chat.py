import ollama

client = ollama.Client(host="http://68.178.160.26:11434")

MODEL = "qwen2.5:7b"

messages = [
    {
        "role": "system",
        "content": (
            "You are an expert AI assistant. "
            "Help with programming, SQL, FastAPI, Streamlit, "
            "AI agents, debugging, and project management. , coding also."
        )
    }
]

print("=" * 60)
print("Qwen2.5:7B Chat")
print("Type 'exit' to quit")
print("=" * 60)

while True:
    user_input = input("\nYou: ")

    if user_input.lower() in ("exit", "quit"):
        break

    messages.append({"role": "user", "content": user_input})

    try:
        response = client.chat(
            model=MODEL,
            messages=messages
        )

        answer = response["message"]["content"]

        print("\nAI:", answer)

        messages.append({"role": "assistant", "content": answer})

    except Exception as e:
        print("\nError:", e)