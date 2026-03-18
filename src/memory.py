import os
from datetime import datetime

def save_log(prompt, response):
    os.makedirs("logs", exist_ok=True)

    with open("logs/history.txt", "a") as f:
        f.write(f"{datetime.now()}\n")
        f.write(f"PROMPT: {prompt}\n")
        f.write(f"RESPONSE: {response}\n\n")