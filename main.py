from src.api_client import call_openai
import os
import json

# List of prompts (can expand later)
prompts = [
    "Hello, how are you?",
    "Give me a short poem about AI",
    "Explain quantum physics in simple terms"
]

# Store all results
results = {}

for i, prompt in enumerate(prompts, 1):
    print(f"\nPrompt {i}: {prompt}")
    response = call_openai(prompt)
    if response:
        print("OpenAI response:")
        print(response)
        results[prompt] = response
    else:
        print("No response received. Check API key or network.")

# Save all responses safely to logs
os.makedirs("logs", exist_ok=True)
log_path = os.path.join("logs", "all_prompts_responses.json")
with open(log_path, "w") as f:
    json.dump(results, f, indent=4)

print(f"\nAll responses saved to {log_path}")