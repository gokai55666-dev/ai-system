# src/smart_router.py
def route_prompt(prompt, sensitivity="auto"):
    """
    Routes to Freedom-AI (local) if uncensored/NSFW detected,
    Routes to RunPod (cloud) for general tasks
    """
    if sensitivity == "nsfw" or detect_uncensored_keyword(prompt):
        return call_freedom_ai_ollama(prompt)  # GGUF, uncensored
    else:
        return call_runpod_vllm(prompt)  # Fast, censored model
