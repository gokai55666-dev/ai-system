# THE core logic

---




from llm import generate
from memory import save_log

def run_pipeline(prompt):
    response = generate(prompt)
    save_log(prompt, response)
    return response