from nodes.llm import call_llm

print("Testing OpenAI connection...")
reply = call_llm("Say 'connection works' and nothing else.")
print("Model replied:", reply)

