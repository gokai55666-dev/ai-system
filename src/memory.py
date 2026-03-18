import os

def save_log(prompt, response):
    os.makedirs("logs", exist_ok=True)
    with open("logs/log.txt", "a") as f:
        f.write(f"{prompt} -> {response}\n")