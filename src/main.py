
from pipeline import run_pipeline

def main():
    while True:
        prompt = input("\nYou: ")

        if prompt.lower() in ["exit", "quit"]:
            break

        response = run_pipeline(prompt)
        print(f"\nAI: {response}")

if __name__ == "__main__":
    main()

---


from pipeline import run_pipeline

def main():
    prompt = input(">> ")
    response = run_pipeline(prompt)
    print(response)

if __name__ == "__main__":
    main()

---

from src.api_client import call_openai
import os
import json

# --- Configuration and Setup ---
# Ensure the 'logs' directory exists for storing responses.
os.makedirs("logs", exist_ok=True)

# --- Prompt Definition ---
# Define a list of prompts. For OpenChat, it's crucial to keep individual prompts
# concise and focused on a single task or question to avoid 'going in circles'.
# If a task is complex, break it down into multiple sequential prompts.
prompts = [
    "Hello, how are you today?",
    "Write a very short, cheerful poem about a cat.",
    "Explain the concept of recursion in programming in one sentence."
]

# --- Response Storage ---
# A dictionary to store all prompts and their corresponding responses.
all_responses = {}

# --- Main Execution Loop ---
print("\n--- Starting AI Interaction ---")
for i, prompt in enumerate(prompts, 1):
    print(f"\n[Prompt {i}/{len(prompts)}]: {prompt}")
    
    # Call the AI model via the API client.
    # The `call_openai` function now handles logging of raw API responses.
    response_content = call_openai(prompt)
    
    if response_content:
        print("  [AI Response]:")
        print(f"  {response_content}")
        all_responses[prompt] = response_content
    else:
        print("  [AI Response]: No response received. Check API client logs for details.")
        all_responses[prompt] = "No response received."

# --- Final Output and Logging ---
# Save all collected responses to a single JSON file for easy review.
final_log_path = os.path.join("logs", "summary_all_prompts_responses.json")
with open(final_log_path, "w") as f:
    json.dump(all_responses, f, indent=4)

print(f"\n--- AI Interaction Complete ---")
print(f"All prompt responses summarized and saved to: {final_log_path}")
print("Individual API call logs are available in the 'logs/' directory.")

