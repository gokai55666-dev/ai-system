import os
import json
import requests
from dotenv import load_dotenv

# Load API key
load_dotenv("../configs/.env")
API_KEY = os.getenv("OPENAI_API_KEY")
API_URL = "https://api.openrouter.ai/v1/chat/completions"

def call_openai(prompt: str):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openchat-3.6-8b",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(API_URL, json=data, headers=headers)
    except requests.RequestException as e:
        print("Network or request error:", e)
        return None

    # Save full response to logs
    os.makedirs("../logs", exist_ok=True)
    with open("../logs/api_response.json", "w") as f:
        json.dump(response.json(), f, indent=4)

    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.json()}")
        return None

    choices = response.json().get("choices", [{}])
    message = choices[0].get("message", {}).get("content") if choices else None
    return message
