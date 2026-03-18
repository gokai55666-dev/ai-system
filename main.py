from src.api_client import call_openai

prompt = "Hello, how are you?"

result = call_openai(prompt)

if result:
    print("OpenAI response:")
    print(result)
else:
    print("No response received. Check API key or network.")
