# a2a_graph/demo/tools.py
"""
Sample tool implementations for demonstration purposes.

These tools are simple examples that can be used with the GraphAwareToolProcessor
to showcase its capabilities.
"""

import asyncio
from typing import Dict, Any, List

# Tool implementations
async def weather_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get weather information for a location.
    
    Parameters
    ----------
    args : Dict[str, Any]
        Should contain a "location" key with the name of the location
        
    Returns
    -------
    Dict[str, Any]
        Weather information including temperature, conditions, and humidity
    """
    location = args.get("location", "Unknown")
    print(f"🌤️  Getting weather for {location}")
    
    # Simulate API call
    await asyncio.sleep(0.5)
    
    return {
        "temperature": 22.5,
        "conditions": "Partly Cloudy",
        "humidity": 65.0,
        "location": location
    }

async def calculator_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a calculation.
    
    Parameters
    ----------
    args : Dict[str, Any]
        Should contain:
        - "operation": one of "add", "subtract", "multiply", "divide"
        - "a": first number
        - "b": second number
        
    Returns
    -------
    Dict[str, Any]
        Calculation result
    """
    operation = args.get("operation", "add")
    a = args.get("a", 0)
    b = args.get("b", 0)
    
    print(f"🧮 Calculating {a} {operation} {b}")
    
    # Simulate calculation
    await asyncio.sleep(0.2)
    
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
    else:
        raise ValueError(f"Unknown operation: {operation}")
    
    return {
        "operation": operation,
        "result": result
    }

async def search_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for information.
    
    Parameters
    ----------
    args : Dict[str, Any]
        Should contain a "query" key with the search terms
        
    Returns
    -------
    Dict[str, Any]
        Search results
    """
    query = args.get("query", "")
    print(f"🔍 Searching for: {query}")
    
    # Simulate search
    await asyncio.sleep(1.0)
    
    return {
        "results": [
            {
                "title": f"Result 1 for {query}",
                "url": f"https://example.com/result1",
                "snippet": f"This is a search result about {query}."
            },
            {
                "title": f"Result 2 for {query}",
                "url": f"https://example.com/result2",
                "snippet": f"This is another search result about {query}."
            }
        ]
    }

# Tool registry dictionary for easy import
TOOL_REGISTRY = {
    "weather": weather_tool,
    "calculator": calculator_tool,
    "search": search_tool
}