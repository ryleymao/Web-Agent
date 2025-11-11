# Minimal DOM Based AI Web Agent
# LLM reads DOM and executes actions using Playwright
# Saves screenshots with phash detection

from planner import LLMPlanner
from executor import WebExecutor
from state_detector import StateDetector
from storage import DatasetStorage

class WebAgent:
    # Main agent that coordinates LLM, browser, and storage
    def __init__(self, headless=False, slow_mo=500, use_existing_browser=False):
        # Initialize components
        self.planner = LLMPlanner()
        self.executor = WebExecutor(headless=headless, slow_mo=slow_mo, use_existing_browser=use_existing_browser)
        self.state_detector = StateDetector()

    def execute_task(self, instruction: str):
        # Reset state detector for fresh task to clear previous phash states
        self.state_detector.reset()

        # Step 1: LLM parses instruction to get URL + task
        print(" parsing instruction ")
        task_info = self.planner.parse_instruction(instruction)
        app_name = task_info["app_name"]
        url = task_info["url"]
        task = task_info["task"]
        print(f"   Task: {task}")
        print(f"   URL: {url}")

        # Step 2: Setup storage for this task
        storage = DatasetStorage(task_name=task, app_name=app_name)

        # Step 3: Open browser and navigate
        print(f"   Navigating to {url}...")
        self.executor.navigate(url)
        screenshot = self.executor.get_screenshot()

        # Save initial screenshot
        if self.state_detector.is_new_state(screenshot, force_save=True):
            storage.save_screenshot(screenshot, "00_initial", "Initial page load", url, {"action": "navigate"})

        # Step 4: Main loop where LLM decides actions until done
        step = 0
        max_steps = 10  # Safety limit
        action_history = []  # Track all actions taken
        use_vision_for_step = False  # Optional selective vision

        while step < max_steps:
            step += 1
            print(f"\n    Step {step}/{max_steps}")

            # Extract DOM elements
            print("   Extracting page elements...")
            dom_context = self.executor.extract_dom_context(max_elements=50)
            current_url = self.executor.get_current_url()

            # Show elements found 
            lines = dom_context.split('\n')
            elem_lines = [l for l in lines if l.strip().startswith('[')]
            if elem_lines:
                print(f"   Found {len(elem_lines)} interactive elements:")
            else:
                print(f"    WARNING: Found 0 interactive elements!")

            # Optional selective vision which is used on step 1 or if previous action failed
            screenshot_for_llm = None
            if step == 1 or use_vision_for_step:
                screenshot_for_llm = self.executor.get_screenshot()
                print("    Using vision for this step")

            use_vision_for_step = False  # Reset flag

            # LLM decides next action with optional vision
            print("   Asking LLM for next action...")
            action = self.planner.decide_next_action(
                task=task,
                dom_context=dom_context,
                current_url=current_url,
                action_history=action_history,
                step_number=step,
                screenshot=screenshot_for_llm  # Optional and works with or without vision LLMs
            )

            # Show the LLM's thinking process
            if action.get("thinking"):
                print(f"   Thinking: {action['thinking'][:80]}...")
            if action.get("evaluation_previous_goal"):
                print(f"   Evaluation: {action['evaluation_previous_goal'][:60]}...")
            if action.get("memory"):
                print(f"   Memory: {action['memory']}")
            if action.get("next_goal"):
                print(f"   Next: {action['next_goal']}")

            # Check if task is complete
            if action.get("action") == "stop":
                print(f"   Task complete")
                break

            # Show what action we're taking
            action_desc = action.get("next_goal") or action.get("description", "")
            print(f"   {action['action'].upper()}: {action_desc}")

            # Execute the action
            result = self.executor.execute_action(action)

            # If action failed and we didn't use vision, retry with vision next step
            if not result.get("success") and not screenshot_for_llm:
                print("    Action failed - will use vision on retry")
                use_vision_for_step = True
                step -= 1  # Retry this step
                continue

            # Record action in history so LLM knows what it did
            action_history.append(action)

            # Capture screenshot if needed
            if action.get("capture") in ["post", "both"]:
                screenshot = self.executor.get_screenshot()
                if self.state_detector.is_new_state(screenshot):
                    name = f"{step:02d}_after_{action['action']}"
                    # Use next_goal as description
                    desc = action.get("next_goal") or action.get("description") or action.get("thinking", "")[:50]
                    storage.save_screenshot(screenshot, name, desc, current_url, action)
                    print(f"   Screenshot saved")

        # Step 5: Save the metadata
        storage.save_metadata(instruction, task_info, action_history)

        return {
            "success": True,
            "output_dir": storage.task_dir,
            "screenshots": storage.screenshot_count
        }

    def close(self):
        self.executor.close()


def main():
    print("Enter a task for Agent B")
    print("Type 'quit' to exit\n")

    agent = WebAgent(headless=False, slow_mo=500)

    try:
        while True:
            task = input("Task: ").strip()
            if task.lower() in ['quit', 'exit']:
                break

            result = agent.execute_task(task)
            print(f"Done! Output: {result['output_dir']}\n")
    finally:
        agent.close()


if __name__ == "__main__":
    main()
