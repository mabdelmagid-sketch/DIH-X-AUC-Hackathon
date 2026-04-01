"""
What-If Scenario Simulator.

Lets users ask "What if we run 20% off on pasta?" and get a data-grounded impact analysis.
"""
import json
from typing import Optional

from .tools import ToolExecutor
from .client import LLMClient
from .prompts import SYSTEM_PROMPTS


class ScenarioSimulator:
    """Run what-if scenarios grounded in real data."""

    def __init__(self, llm_client: LLMClient, tool_executor: ToolExecutor):
        self.llm = llm_client
        self.tools = tool_executor

    async def simulate(self, scenario: str) -> str:
        """
        Run a what-if simulation. Gathers relevant data then asks the LLM to analyze.

        The LLM will use function-calling to gather the data it needs,
        then synthesize an impact analysis.
        """
        prompt = f"""The user wants to simulate a scenario. Analyze this what-if question:

"{scenario}"

Follow these steps:
1. Use the available tools to look up relevant current data (inventory levels, sales history, menu items, BOM)
2. Based on the real data, estimate the impact of this scenario on:
   - Demand changes (use historical data to ground estimates)
   - Supply/ingredient requirements
   - Revenue impact
   - Waste impact
3. Give a clear recommendation: should they do it, with what modifications?

Be quantitative and ground everything in the actual data you retrieve."""

        return await self.llm.chat_with_tools(
            user_message=prompt,
            system_prompt=SYSTEM_PROMPTS["simulator"],
            temperature=0.5
        )
