from pipeline import run_pipeline

def main():
    print("AI System Ready. Type 'exit' to quit.\n")

    while True:
        try:
            prompt = input("You: ").strip()

            if not prompt:
                continue

            if prompt.lower() in ["exit", "quit"]:
                print("Exiting...")
                break

            response = run_pipeline(prompt)

            print(f"\nAI: {response}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break

        except Exception as e:
            print(f"\n[ERROR] {e}\n")


if __name__ == "__main__":
    main()