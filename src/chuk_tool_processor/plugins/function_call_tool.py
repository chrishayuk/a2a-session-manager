# chuk_tool_processor/plugins/function_call_tool.py
import json
from typing import List, Any, Dict
from pydantic import ValidationError

from chuk_tool_processor.models.tool_call import ToolCall

class FunctionCallPlugin:
    """
    Parse OpenAI-style `function_call` payloads embedded in the LLM response.
    
    Expects raw JSON like:
      {
        "function_call": {
          "name": "my_tool",
          "arguments": '{"x":1,"y":"two"}'
        }
      }
    or, alternatively, if the arguments are already a dict:
      {
        "function_call": {
          "name": "my_tool",
          "arguments": {"x":1, "y":"two"}
        }
      }
    """
    def try_parse(self, raw: str) -> List[ToolCall]:
        calls: List[ToolCall] = []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        
        fc = payload.get("function_call")
        if not isinstance(fc, dict):
            return []
        
        name = fc.get("name")
        args = fc.get("arguments", {})
        
        # Arguments sometimes come back as a JSON-encoded string
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                # leave it as raw string if malformed
                args = {}
        
        # Only proceed if we have a valid name
        if not isinstance(name, str) or not name:
            return []
        
        try:
            call = ToolCall(tool=name, arguments=args if isinstance(args, Dict) else {})
            calls.append(call)
        except ValidationError:
            # invalid tool name or args shape
            pass
        
        return calls
