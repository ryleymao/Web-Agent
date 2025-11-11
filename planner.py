# LLM Planner that decides what actions to take
# Uses LLM to parse instructions and decide next actions

import json
import os
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class LLMPlanner:

    def __init__(self):
        # Initialize
        self.provider = os.getenv('LLM_PROVIDER', 'gemini').lower()
        self.model_name = os.getenv('LLM_MODEL')

        # Initialize the selected provider
        if self.provider == 'gemini':   
            import google.generativeai as genai
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            self.client = genai.GenerativeModel(self.model_name or 'gemini-2.0-flash-exp')

        elif self.provider == 'openai':
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            self.model_name = self.model_name or 'gpt-4o-mini'

        elif self.provider == 'groq':
            from groq import Groq
            self.client = Groq(api_key=os.getenv('GROQ_API_KEY'))
            self.model_name = self.model_name or 'llama-3.3-70b-versatile'

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}. Use 'openai', 'gemini', or 'groq'")

    def parse_instruction(self, instruction: str) -> Dict[str, Any]:
        # Parse user instruction into structured task info
        prompt = PARSE_PROMPT.format(instruction=instruction)

        # Ask LLM
        response = self._call_llm(prompt)

        # Parse JSON response
        result = self._parse_json(response)
        return result

    def decide_next_action(
        self,
        task: str,
        dom_context: str,
        current_url: str,
        action_history: List[Dict],
        step_number: int,
        screenshot: bytes = None
    ) -> Dict[str, Any]:
        # Decide next action based on current state
        history_text = "\n".join([
            f"  {i+1}. {a['action']}: {a.get('next_goal') or a.get('description', 'action taken')}"
            for i, a in enumerate(action_history[-5:])
        ]) if action_history else "None yet"

        # Add vision indicator if screenshot provided
        vision_note = "[You can see the page]" if screenshot else "[DOM only]"

        # Format prompt with current state
        prompt = ACTION_PROMPT.format(
            task=task,
            dom_context=dom_context,
            current_url=current_url,
            action_history=history_text,
            vision_note=vision_note
        )

        # Ask LLM for next action with optional vision and structured output
        response = self._call_llm(prompt, image=screenshot, use_structured_output=True)

        # Parse action
        parsed = self._parse_json(response)

        # Convert action format to executor format
        action_list = parsed.get('action', [])
        action_obj = {}
        text_value = ''

        # Handle case where LLM returns wrong format that is flat instead of nested
        if not isinstance(action_list, list):
            # LLM returned wrong format and try to salvage it
            print(f"    WARNING: LLM returned wrong action format. Trying to parse...")
            # Check if it's a flat dict 
            if 'action' in parsed and isinstance(parsed['action'], str):
                flat_action = parsed.get('action')
                if flat_action in ['click', 'click_element'] and 'index' in parsed:
                    action_list = [{'click_element': {'index': parsed['index']}}]
                elif flat_action in ['input', 'input_text'] and 'index' in parsed:
                    action_list = [{'input_text': {'index': parsed['index'], 'text': parsed.get('text', '')}}]
                else:
                    action_list = []
            else:
                action_list = []

        if action_list and len(action_list) > 0:
            action_obj = action_list[0]  # Get first action

            # Extract action type and params
            if 'click_element' in action_obj:
                index = action_obj['click_element'].get('index')
                action_type = 'click'
                selector = f'[{int(index)}]'
                print(f"   Parsed: CLICK element [{int(index)}]")
            elif 'input_text' in action_obj:
                index = action_obj['input_text'].get('index')
                text_value = action_obj['input_text'].get('text', '')
                action_type = 'type'
                selector = f'[{int(index)}]'
                print(f"   Parsed: TYPE '{text_value}' into element [{int(index)}]")
            elif 'done' in action_obj:
                action_type = 'stop'
                selector = None
                print(f"   Parsed: DONE")
            else:
                action_type = 'wait'
                selector = None
                print(f"    Unknown action type, defaulting to WAIT")
        else:
            action_type = 'wait'
            selector = None
            print(f"    No action found in response, defaulting to WAIT")

        # Build action in our format
        action = {
            'action': action_type,
            'selector': selector,
            'text': text_value,
            'thinking': parsed.get('thinking', ''),
            'memory': parsed.get('memory', ''),
            'next_goal': parsed.get('next_goal', ''),
            'capture': 'both',
            'step_number': step_number
        }

        return action

    def _call_llm(self, prompt: str, image: bytes = None, use_structured_output: bool = False) -> str:
        # Call the LLM API with optional vision support and structured JSON output
        if self.provider == 'gemini':
            if image:
                import PIL.Image
                import io
                img = PIL.Image.open(io.BytesIO(image))
                response = self.client.generate_content([prompt, img])
            else:
                response = self.client.generate_content(prompt)
            return response.text

        elif self.provider in ['openai', 'groq']:
            # Build message content
            if image and self.provider == 'openai':
                # For OpenAI vision support
                import base64
                b64_image = base64.b64encode(image).decode('utf-8')
                user_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}", "detail": "low"}}
                ]
            else:
                # Text only
                user_content = prompt

            # Use JSON mode for OpenAI with strict format enforcement
            if use_structured_output and self.provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a web automation expert. Respond with valid JSON in the EXACT format shown in the examples."},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    timeout=30.0
                )
                return response.choices[0].message.content
            else:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a web automation expert. Always respond with valid JSON."},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.3,
                    timeout=30.0
                )
                return response.choices[0].message.content

    def _parse_json(self, response: str) -> Dict[str, Any]:
        # Extract JSON from LLM response, this handles markdown code blocks
        try:
            # Strip markdown code blocks if present
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            return json.loads(response)

        except json.JSONDecodeError as e:
            print(f"  Failed to parse LLM response: {e}")
            print(f"Response: {response[:200]}...")
            # Safe fallback
            return {"action": "stop", "description": "Failed to parse action"}


# PROMPTS FOR LLM

PARSE_PROMPT = """Parse: {instruction}

Extract app, URL, task.

JSON: {{"app_name":"...", "url":"https://...", "task":"..."}}

Example: "filter database in Notion" → {{"app_name":"Notion", "url":"https://notion.so", "task":"filter database"}}
"""

ACTION_PROMPT = """You are controlling a web browser to complete this task: {task}

INTERACTIVE ELEMENTS ON PAGE:
{dom_context}

WHAT YOU'VE DONE SO FAR:
{action_history}

IMPORTANT RULES:
1. ONLY use index numbers from the elements list above [1] to [40]
2. Read element text carefully before clicking - make sure it matches your goal
3. For search boxes: ONLY type the text - search will submit automatically (don't click search buttons)
4. After typing in a search box, wait one step to see results before doing anything else
5. Take ONE action at a time - don't rush
6. If task is complete, use done action

You MUST respond with this EXACT JSON structure:

{{
  "thinking": "what I see and which element I need",
  "evaluation_previous_goal": "did my last action work",
  "memory": "progress made so far",
  "next_goal": "specific next step",
  "action": [{{CHOOSE ONE ACTION BELOW}}]
}}

ACTION OPTIONS (use EXACTLY one):

1. CLICK: {{"click_element": {{"index": 5}}}}
2. TYPE: {{"input_text": {{"index": 3, "text": "your text here"}}}}
3. DONE: {{"done": {{"text": "task complete", "success": true}}}}

EXAMPLE - Clicking a button:
{{
  "thinking": "I need the 'Create Project' button. I see it at index 12",
  "evaluation_previous_goal": "Successfully navigated to projects page",
  "memory": "On projects page, ready to create new project",
  "next_goal": "Click 'Create Project' button at index 12",
  "action": [{{"click_element": {{"index": 12}}}}]
}}

EXAMPLE - Typing in search:
{{
  "thinking": "I need to search. I see the search input at index 5",
  "evaluation_previous_goal": "Page loaded successfully",
  "memory": "On YouTube homepage",
  "next_goal": "Type 'funny cats' in search box at index 5",
  "action": [{{"input_text": {{"index": 5, "text": "funny cats"}}}}]
}}

Now respond with valid JSON:"""
