# Agent A for interactive CLI
# Run: python agent_a_to_b.py

import sys
import subprocess
import os
from agent_b import WebAgent


def setup_chrome():
    # Start Chrome with debugging enabled works cross-platform
    import platform
    system = platform.system()

    if system == "Darwin":  # Mac
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Windows":
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if not os.path.exists(chrome_path):
            chrome_path = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
    else:  # Linux
        chrome_path = "/usr/bin/google-chrome"

    # Check if Chrome exists
    if not os.path.exists(chrome_path):
        print(f" Chrome not found at: {chrome_path}")
        return False

    print(" Starting Chrome...")
    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={os.path.expanduser('~/chrome-debug-profile')}"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return True


def connect_to_chrome():
    # Try to connect to existing Chrome
    try:
        agent = WebAgent(use_existing_browser=True, slow_mo=50)
        return agent
    except RuntimeError:
        # Chrome not running so start it
        print("  Chrome not running with debugging enabled")
        if setup_chrome():
            import time
            print(" Waiting for Chrome to start...")
            time.sleep(3)
            try:
                agent = WebAgent(use_existing_browser=True, slow_mo=50)
                return agent
            except RuntimeError:
                print(" Could not connect to Chrome")
                print("Please start Chrome manually:")
                print("  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
                return None
        return None


def main():
    print("=" * 60)
    print(" Agent A is running")
    print()

    # Connect to Chrome or start it
    agent = connect_to_chrome()
    if not agent:
        sys.exit(1)

    current_url = agent.executor.get_current_url()
    print(f" Connected to Chrome")
    print(f" Current page: {current_url}")
    print()

    # Interactive loop
    while True:
        try:
            question = input("What do you want to ask Agent B? ('quit' to exit): ").strip()

            if not question:
                continue

            if question.lower() in ['quit', 'exit', 'q']:
                print("\n Goodbye! Browser will stay open.")
                break

            # Process question
            print()
            print("  Processing...")
            print()

            result = agent.execute_task(question)

            print()
            if result["success"]:
                print(" TASK COMPLETED ")
                print(f"\n Dataset: {result['output_dir']}")
                print(f" Screenshots: {result['screenshots']}")
            else:
                print(" TASK FAILED ")
                print(f"Error: {result.get('error')}")
            print()

        except KeyboardInterrupt:
            print("\n\n Goodbye! Browser will stay open.")
            break
        except Exception as e:
            print(f"\n Error: {e}")
            print()


if __name__ == "__main__":
    main()
