import os
import json
import requests
from dotenv import load_dotenv

# Load API key from .env file in the configs directory
load_dotenv("configs/.env")

API_KEY = os.getenv("OPENAI_API_KEY")
API_URL = "https://api.openrouter.ai/v1/chat/completions"

def call_openai(prompt: str):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "openchat/openchat-3.6-8b", # Using OpenChat as requested
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()  # Raise an exception for HTTP errors
        response_json = response.json()
        
        # Log full response for debugging
        os.makedirs("logs", exist_ok=True)
        with open(f"logs/api_response_{len(os.listdir('logs'))}.json", "w") as f:
            json.dump(response_json, f, indent=4)

        choices = response_json.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("content")
        else:
            print("No choices found in API response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network or request error: {e}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON response.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

