"""
OpenRouter LLM Client with function-calling support.
"""
import httpx
import json
from typing import Optional, AsyncIterator

from ..config import settings
from .tools import TOOL_DEFINITIONS, ToolExecutor


class LLMClient:
    """Client for OpenRouter API with function-calling and streaming."""

    MAX_TOOL_ROUNDS = 5  # Prevent infinite loops

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.default_llm
        self.tool_executor: Optional[ToolExecutor] = None

        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

    def set_tool_executor(self, executor: ToolExecutor):
        """Set the tool executor for function-calling."""
        self.tool_executor = executor

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://flowpos.app",
            "X-Title": "FlowPOS Demand Intelligence"
        }

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Send a simple chat completion request (no tools)."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            if stream:
                return self._stream_response(client, payload)
            else:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

    async def chat_with_tools(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[list[dict]] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> str:
        """Chat with function-calling support. Runs tool loops until LLM gives a text response."""
        from .prompts import SYSTEM_PROMPTS

        messages = []

        # System prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": SYSTEM_PROMPTS["chat_assistant"]})

        # Conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # User message
        messages.append({"role": "user", "content": user_message})

        # Tool-calling loop
        for _ in range(self.MAX_TOOL_ROUNDS):
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto"
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            # If the model wants to call tools
            if message.get("tool_calls"):
                # Add assistant message with tool calls
                messages.append(message)

                # Execute each tool call
                for tool_call in message["tool_calls"]:
                    fn = tool_call["function"]
                    tool_name = fn["name"]
                    try:
                        arguments = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    except json.JSONDecodeError:
                        arguments = {}

                    # Execute the tool (async-aware)
                    if self.tool_executor:
                        result = await self.tool_executor.execute_async(tool_name, arguments)
                    else:
                        result = json.dumps({"error": "Tool executor not configured"})

                    # Add tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })

                # Continue the loop to let the model process tool results
                continue

            # No tool calls - return the text response
            content = message.get("content") or ""
            if content:
                return content

            # DeepSeek sometimes returns content=null after tool rounds;
            # retry once without tools to force a text response
            messages.append(message)
            messages.append({"role": "user", "content": "Please provide your analysis based on the data you gathered."})
            retry_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                retry_resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=retry_payload
                )
                retry_resp.raise_for_status()
                retry_data = retry_resp.json()
            return retry_data["choices"][0]["message"].get("content") or "Unable to generate analysis. Please try again."

        # Exhausted rounds
        return "I gathered a lot of data but couldn't fully synthesize an answer. Could you ask a more specific question?"

    async def chat_with_tools_stream(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[list[dict]] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> AsyncIterator[str]:
        """
        Chat with function-calling, yielding SSE events.

        Yields events in the format:
          data: {"type": "tool_call", "tool": "...", "args": {...}}
          data: {"type": "token", "content": "..."}
          data: {"type": "done"}
        """
        from .prompts import SYSTEM_PROMPTS

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": SYSTEM_PROMPTS["chat_assistant"]})

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        # Tool-calling rounds (non-streaming, since we need complete tool calls)
        for _ in range(self.MAX_TOOL_ROUNDS):
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto"
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            if message.get("tool_calls"):
                messages.append(message)

                for tool_call in message["tool_calls"]:
                    fn = tool_call["function"]
                    tool_name = fn["name"]
                    try:
                        arguments = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    except json.JSONDecodeError:
                        arguments = {}

                    # Notify client that a tool is being called
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'args': arguments})}\n\n"

                    if self.tool_executor:
                        result = await self.tool_executor.execute_async(tool_name, arguments)
                    else:
                        result = json.dumps({"error": "Tool executor not configured"})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })

                continue

            # Final response - stream it token by token
            # Make a new streaming request with the full conversation
            payload["stream"] = True
            # Remove tools for the final streaming call to avoid issues
            del payload["tools"]
            del payload["tool_choice"]

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload
                ) as stream_response:
                    stream_response.raise_for_status()
                    async for line in stream_response.aiter_lines():
                        if line.startswith("data: "):
                            raw = line[6:]
                            if raw == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw)
                                content = chunk["choices"][0].get("delta", {}).get("content")
                                if content:
                                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                            except json.JSONDecodeError:
                                continue

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'token', 'content': 'I gathered data but could not fully synthesize. Try a more specific question.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # --- Convenience methods (kept from original) ---

    async def generate_insights(
        self,
        context: dict,
        query: Optional[str] = None
    ) -> str:
        """Generate inventory insights based on context."""
        from .prompts import SYSTEM_PROMPTS

        system_prompt = SYSTEM_PROMPTS["inventory_analyst"]

        context_parts = []
        if "current_stock" in context:
            context_parts.append(f"**Current Stock Levels:**\n{context['current_stock']}")
        if "forecasts" in context:
            context_parts.append(f"**Demand Forecasts (Next 7 Days):**\n{context['forecasts']}")
        if "expiring_items" in context:
            context_parts.append(f"**Items Expiring Soon:**\n{context['expiring_items']}")
        if "low_stock_alerts" in context:
            context_parts.append(f"**Low Stock Alerts:**\n{context['low_stock_alerts']}")
        if "recent_sales" in context:
            context_parts.append(f"**Recent Sales Trends:**\n{context['recent_sales']}")
        if "store_info" in context:
            context_parts.insert(0, f"**IMPORTANT - This Store's Actual Menu & Products (base ALL analysis on these):**\n{context['store_info']}\n\nOnly discuss items from this store's menu. Do not reference items not on the menu.")
        if "business_rules" in context:
            context_parts.append(f"**Business Rules:**\n{context['business_rules']}")

        context_message = "\n\n".join(context_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the current inventory situation:\n\n{context_message}"}
        ]

        if query:
            messages.append({"role": "user", "content": f"Specific question: {query}"})
        else:
            messages.append({"role": "user", "content": "Please provide a daily briefing with key insights and recommended actions."})

        return await self.chat(messages)

    async def explain_anomaly(
        self,
        item: str,
        expected: float,
        actual: float,
        context: dict
    ) -> str:
        """Explain why actual sales differed from forecast."""
        from .prompts import SYSTEM_PROMPTS

        diff_pct = ((actual - expected) / expected * 100) if expected > 0 else 0
        direction = "higher" if actual > expected else "lower"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS["anomaly_explainer"]},
            {
                "role": "user",
                "content": f"""Analyze this sales anomaly:

**Item:** {item}
**Expected Sales:** {expected:.0f} units
**Actual Sales:** {actual:.0f} units
**Difference:** {abs(diff_pct):.1f}% {direction} than expected

**Context:**
- Day: {context.get('day_of_week', 'Unknown')}
- Weather: {context.get('weather', 'Unknown')}
- Active Promotions: {context.get('promotions', 'None')}
- Recent Events: {context.get('events', 'None')}

Why did this happen and what should we do?"""
            }
        ]

        return await self.chat(messages, temperature=0.5)

    async def suggest_promotion(
        self,
        item: str,
        current_stock: float,
        days_to_expiry: int,
        avg_daily_sales: float,
        cost: float,
        price: float
    ) -> str:
        """Suggest a promotion for expiring inventory."""
        from .prompts import SYSTEM_PROMPTS

        margin = (price - cost) / price * 100 if price > 0 else 0
        days_of_stock = current_stock / avg_daily_sales if avg_daily_sales > 0 else float('inf')

        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS["promo_strategist"]},
            {
                "role": "user",
                "content": f"""Help me create a promotion for this expiring item:

**Item:** {item}
**Current Stock:** {current_stock:.0f} units
**Days Until Expiry:** {days_to_expiry}
**Average Daily Sales:** {avg_daily_sales:.1f} units
**Days of Stock at Current Rate:** {days_of_stock:.1f}
**Cost per Unit:** {cost:.2f} DKK
**Current Price:** {price:.2f} DKK
**Current Margin:** {margin:.1f}%

Suggest:
1. Recommended discount percentage
2. Promotion name/messaging
3. Target quantity to move
4. Expected margin impact
5. Alternative uses (if applicable)"""
            }
        ]

        return await self.chat(messages, temperature=0.7)
