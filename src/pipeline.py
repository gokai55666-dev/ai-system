from llm import generate
from memory import save_log  # optional, you can create this later

def run_pipeline(prompt):
    """
    Simple pipeline: generate response and optionally save log.
    """
    response = generate(prompt)
    save_log(prompt, response)  # if memory module is missing, comment this line
    return response