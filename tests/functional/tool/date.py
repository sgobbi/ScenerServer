from agent.api import AgentAPI
from datetime import datetime
import pytest


@pytest.fixture(scope="function")
def llm_agent():
    def ask(prompt: str) -> dict:
        api = AgentAPI()
        return api.ask(prompt)

    return ask


def test_agent_uses_date_tool(llm_agent):
    """Basic test to check if the agent uses the date tool correctly."""
    prompt = "What is today's date?"
    ret = llm_agent(prompt)
    tools_used = [tool.lower() for tool in ret["tools"]]

    # Should call date tool only
    assert "date" in tools_used
    assert len(tools_used) == 1
