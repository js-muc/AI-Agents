"""
Bounded Serper Tool
A Serper search tool with a hard cap on the number of calls per run.

Why this exists:
    CrewAI's SerperDevTool allows the LLM to issue unlimited parallel tool
    calls within a single reasoning iteration. An eager LLM can produce
    hundreds of searches in seconds, overflowing the model's context window.

    This tool tracks call count and returns a refusal message once the cap
    is reached. The LLM sees the refusal and stops issuing new searches.

Usage:
    In an agent's tools list, use "custom:bounded_serper_tool" instead of
    "SerperDevTool".
"""

import os
import requests
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field


# Hard limit: maximum searches allowed per tool instance
MAX_SEARCHES = 5


class BoundedSerperInput(BaseModel):
    """Input schema for the Bounded Serper Tool."""
    search_query: str = Field(
        ...,
        description="The search query string. Example: 'benefits of drinking water'"
    )


class BoundedSerperTool(BaseTool):
    """Serper search tool with a hard cap on the number of calls.

    Uses the Serper API directly (via requests) rather than wrapping
    CrewAI's SerperDevTool, so there is no nested BaseTool dependency.
    """

    name: str = "search_the_internet_with_serper"
    description: str = (
        "Search the internet using Serper. Returns the top results for a query. "
        "A hard limit is enforced on the total number of searches per run."
    )
    args_schema: Type[BaseModel] = BoundedSerperInput

    # Instance state — set up via private attributes
    _call_count: int = 0

    def _run(self, search_query: str) -> str:
        """Perform a web search with a hard call cap."""
        # Enforce the hard cap
        if self._call_count >= MAX_SEARCHES:
            return (
                f"[SEARCH LIMIT REACHED] You have already performed "
                f"{self._call_count} searches (the maximum allowed is {MAX_SEARCHES}). "
                f"Do NOT issue further searches. Analyze the results you already "
                f"have and produce your final answer now."
            )

        self._call_count += 1
        print(f"[BoundedSerperTool] Search #{self._call_count}/{MAX_SEARCHES}: {search_query[:60]}")

        # Call Serper API directly
        api_key = os.environ.get("SERPER_API_KEY", "")
        if not api_key:
            return "Error: SERPER_API_KEY not set in environment."

        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"q": search_query, "num": 5},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            # Format results compactly
            organic = data.get("organic", [])[:5]
            if not organic:
                return f"No results found for: {search_query}"

            lines = [f"Search results for '{search_query}':"]
            for i, item in enumerate(organic, 1):
                title = item.get("title", "")[:80]
                snippet = item.get("snippet", "")[:200]
                link = item.get("link", "")
                lines.append(f"{i}. {title}")
                lines.append(f"   {snippet}")
                lines.append(f"   Source: {link}")
            return "\n".join(lines)

        except requests.exceptions.Timeout:
            return f"Search timed out for: {search_query}"
        except requests.exceptions.RequestException as e:
            return f"Search request failed: {e}"
        except Exception as e:
            return f"Search error: {e}"
