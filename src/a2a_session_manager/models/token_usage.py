# a2a_session_manager/models/token_usage.py
"""
Token usage tracking models for the A2A Session Manager.

This module provides models for tracking token usage in LLM interactions.
It optionally uses tiktoken for accurate token counting if available.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Optional, Union, List, Any, overload
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict

# Try to import tiktoken, but make it optional
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


class TokenUsage(BaseModel):
    """
    Tracks token usage for LLM interactions.
    
    Attributes:
        prompt_tokens: Number of tokens in the prompt/input
        completion_tokens: Number of tokens in the completion/output
        total_tokens: Total tokens (prompt + completion)
        model: The model used for the interaction (helps with pricing calculations)
        estimated_cost_usd: Estimated cost in USD (if pricing info is available)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = Field(default=0)
    model: str = ""
    estimated_cost_usd: Optional[float] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        # Auto-calculate total tokens if not explicitly provided
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            self.total_tokens = self.prompt_tokens + self.completion_tokens
            
        # Auto-calculate estimated cost if model is provided
        if self.model and self.estimated_cost_usd is None:
            self.estimated_cost_usd = self.calculate_cost()
    
    def calculate_cost(self) -> float:
        """
        Calculate the estimated cost based on the model and token counts.
        
        Returns:
            Estimated cost in USD
        """
        # Model pricing per 1000 tokens (approximate as of May 2025)
        # This should be updated as pricing changes
        pricing = {
            # OpenAI models
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            
            # Claude models
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
            
            # Fallback for unknown models
            "default": {"input": 0.001, "output": 0.002}
        }
        
        # Get pricing for this model or use default
        model_pricing = pricing.get(self.model.lower(), pricing["default"])
        
        # Calculate cost
        input_cost = (self.prompt_tokens / 1000) * model_pricing["input"]
        output_cost = (self.completion_tokens / 1000) * model_pricing["output"]
        
        return round(input_cost + output_cost, 6)
    
    # Async version as a separate method
    async def calculate_cost(self) -> float:
        """
        Async version of calculate_cost.
        
        Returns:
            Estimated cost in USD
        """
        return self.calculate_cost()
    
    def update(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """
        Update token counts and recalculate totals and costs.
        
        Args:
            prompt_tokens: Additional prompt tokens to add
            completion_tokens: Additional completion tokens to add
        """
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        
        if self.model:
            self.estimated_cost_usd = self.calculate_cost()
    
    # Async version as a separate method
    async def update(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """
        Async version of update.
        
        Args:
            prompt_tokens: Additional prompt tokens to add
            completion_tokens: Additional completion tokens to add
        """
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        
        if self.model:
            self.estimated_cost_usd = await self.calculate_cost()
    
    @classmethod
    def from_text(
        cls, 
        prompt: str, 
        completion: Optional[str] = None, 
        model: str = "gpt-3.5-turbo"
    ) -> TokenUsage:
        """
        Create a TokenUsage instance by counting tokens in the provided text.
        
        Args:
            prompt: The prompt/input text
            completion: The completion/output text (optional)
            model: The model name to use for counting and pricing
            
        Returns:
            A TokenUsage instance with token counts
            
        Note:
            If tiktoken is not available, a simple approximation is used.
        """
        prompt_tokens = cls.count_tokens(prompt, model)
        completion_tokens = cls.count_tokens(completion, model) if completion else 0
        
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model
        )
    
    # Async version as a separate method 
    @classmethod
    async def from_text(
        cls, 
        prompt: str, 
        completion: Optional[str] = None, 
        model: str = "gpt-3.5-turbo"
    ) -> TokenUsage:
        """
        Async version of from_text.
        
        Args:
            prompt: The prompt/input text
            completion: The completion/output text (optional)
            model: The model name to use for counting and pricing
            
        Returns:
            A TokenUsage instance with token counts
        """
        # Token counting is CPU-bound, not I/O bound
        return cls.from_text(prompt, completion, model)
    
    @staticmethod
    def count_tokens(text: Optional[str], model: str = "gpt-3.5-turbo") -> int:
        """
        Count the number of tokens in the provided text.
        
        Args:
            text: The text to count tokens for
            model: The model name to use for counting
            
        Returns:
            The number of tokens
            
        Note:
            If tiktoken is not available, a simple approximation is used.
        """
        if text is None:
            return 0
            
        if TIKTOKEN_AVAILABLE:
            try:
                encoding = tiktoken.encoding_for_model(model)
                return len(encoding.encode(text))
            except (KeyError, ValueError):
                # Fall back to cl100k_base encoding if the model is not found
                try:
                    encoding = tiktoken.get_encoding("cl100k_base")
                    return len(encoding.encode(text))
                except Exception:
                    # If all else fails, use the approximation
                    pass
        
        # Simple approximation: ~4 chars per token for English text
        # This is a very rough estimate and shouldn't be relied upon for billing
        return int(len(text) / 4)
    
    # Async version as a separate method
    @staticmethod
    async def count_tokens(text: Optional[str], model: str = "gpt-3.5-turbo") -> int:
        """
        Async version of count_tokens.
        
        Args:
            text: The text to count tokens for
            model: The model name to use for counting
            
        Returns:
            The number of tokens
        """
        # Token counting is CPU-bound, not I/O bound
        return TokenUsage.count_tokens(text, model)
    
    def __add__(self, other: TokenUsage) -> TokenUsage:
        """
        Add two TokenUsage instances together.
        
        Args:
            other: Another TokenUsage instance
            
        Returns:
            A new TokenUsage instance with combined counts
        """
        # Use the model from self if it exists, otherwise use the other's model
        model = self.model if self.model else other.model
        
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            model=model
        )


class TokenSummary(BaseModel):
    """
    Summarizes token usage across multiple interactions.
    
    Attributes:
        total_prompt_tokens: Total tokens used in prompts
        total_completion_tokens: Total tokens used in completions
        total_tokens: Total tokens overall
        usage_by_model: Breakdown of usage by model
        total_estimated_cost_usd: Total estimated cost across all models
    """
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    usage_by_model: Dict[str, TokenUsage] = Field(default_factory=dict)
    total_estimated_cost_usd: float = 0.0
    
    def add_usage(self, usage: TokenUsage) -> None:
        """
        Add a TokenUsage instance to this summary.
        
        Args:
            usage: The TokenUsage to add
        """
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        
        if usage.estimated_cost_usd is not None:
            self.total_estimated_cost_usd += usage.estimated_cost_usd
        
        if usage.model:
            if usage.model in self.usage_by_model:
                self.usage_by_model[usage.model].update(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens
                )
            else:
                self.usage_by_model[usage.model] = TokenUsage(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    model=usage.model
                )
                
    # Async version as a separate method
    async def add_usage(self, usage: TokenUsage) -> None:
        """
        Async version of add_usage.
        
        Args:
            usage: The TokenUsage to add
        """
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        
        if usage.estimated_cost_usd is not None:
            self.total_estimated_cost_usd += usage.estimated_cost_usd
        
        if usage.model:
            if usage.model in self.usage_by_model:
                await self.usage_by_model[usage.model].update(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens
                )
            else:
                self.usage_by_model[usage.model] = TokenUsage(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    model=usage.model
                )