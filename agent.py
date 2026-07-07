import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client

# Tool definitions — what the agent can do
# Each tool maps to a function in /tools/
TOOLS = [
    {
        "name": "parse_input",
        "description": "Parse natural language into a structured schedule item candidate. Always returns needs_confirmation: true — never places directly.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The natural language input from the user"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "place_item",
        "description": "Place a confirmed schedule item. Only called after user explicitly confirms. Runs conflict detection automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "object",
                    "description": "The confirmed ScheduleItem to place"
                }
            },
            "required": ["item"]
        }
    },
    {
        "name": "check_deadline",
        "description": "Check deadline status for a priority. Returns hours remaining, tasks left, time needed, available blocks, and whether it fits.",
        "parameters": {
            "type": "object",
            "properties": {
                "priority_id": {
                    "type": "string",
                    "description": "The ID of the priority to check"
                }
            },
            "required": ["priority_id"]
        }
    },
    {
        "name": "get_coach_response",
        "description": "Generate a coaching response grounded in the user's schedule, daily log, and deadline context.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The user's message"
                },
                "priority_id": {
                    "type": "string",
                    "description": "Optional priority ID for deadline-aware coaching"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "breakdown_tasks",
        "description": "Break a priority into concrete actionable tasks with time estimates and quality targets.",
        "parameters": {
            "type": "object",
            "properties": {
                "priority": {
                    "type": "object",
                    "description": "The priority to break down"
                }
            },
            "required": ["priority"]
        }
    }
]

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Executes a tool call from the agent loop.
    Each tool maps to a function in /tools/.
    Returns the result as a string for the agent to reason about.
    """
    from tools.parse_input import parse_input_to_candidate
    from tools.place_item import place_confirmed_item
    from tools.check_deadline import check_deadline
    from tools.coach_response import get_coach_response
    from tools.breakdown_tasks import breakdown_priority

    try:
        if tool_name == "parse_input":
            result = parse_input_to_candidate(tool_input["text"])
        elif tool_name == "place_item":
            result = place_confirmed_item(tool_input["item"])
        elif tool_name == "check_deadline":
            result = check_deadline(tool_input["priority_id"])
        elif tool_name == "get_coach_response":
            result = get_coach_response(
                tool_input["message"],
                tool_input.get("priority_id")
            )
        elif tool_name == "breakdown_tasks":
            result = breakdown_priority(tool_input["priority"])
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result)

    except Exception as e:
        return json.dumps({"error": str(e)})


def load_agents() -> str:
    """
    Loads the agent's identity and rules from AGENTS.md.
    This is the system prompt — it defines how the agent reasons,
    what it protects, and how it communicates.
    """
    agent_path = os.path.join(os.path.dirname(__file__), "AGENTS.md")
    try:
        with open(agent_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "You are Coach, a pragmatic schedule agent. Never place items without confirmation."


class CoachAgent:
    """
    The main agent class. Manages the conversation loop,
    tool calls, and confirmation flow.

    The agent loop:
    1. Receive user message
    2. Send to Gemini with tools available
    3. If Gemini calls a tool — execute it, feed result back
    4. Repeat until Gemini returns a final response
    5. Return response to user
    """

    def __init__(self):
        self.system_prompt = load_agents()
        self.conversation_history = []

    def chat(self, user_message: str) -> str:
        """
        Main entry point. Takes a user message, runs the agent loop,
        returns the agent's response.
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })

        # Agent loop — keeps running until no more tool calls
        while True:
            response = get_client().models.generate_content(
                model=os.getenv("MODEL", "gemini-3.1-flash-lite"),
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    tools=TOOLS,
                    max_output_tokens=2048
                ),
                contents=self.conversation_history
            )

            # Check if Gemini wants to call a tool
            tool_calls = [
                part for part in response.candidates[0].content.parts
                if hasattr(part, "function_call") and part.function_call
            ]

            if not tool_calls:
                # No tool calls — we have the final response
                final_text = response.text
                self.conversation_history.append({
                    "role": "model",
                    "parts": [{"text": final_text}]
                })
                return final_text

            # Execute each tool call and feed results back
            tool_results = []
            for part in tool_calls:
                tool_name = part.function_call.name
                tool_input = dict(part.function_call.args)
                result = execute_tool(tool_name, tool_input)
                tool_results.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": result}
                    }
                })

            # Add tool results to history and loop again
            self.conversation_history.append({
                "role": "model",
                "parts": [part for part in response.candidates[0].content.parts]
            })
            self.conversation_history.append({
                "role": "user",
                "parts": tool_results
            })

    def reset(self):
        """Clears conversation history — starts a fresh session."""
        self.conversation_history = []