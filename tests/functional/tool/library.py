from agent.api import AgentAPI
from datetime import datetime
import pytest


@pytest.fixture
def llm_agent():
    def ask(prompt: str) -> dict:
        api = AgentAPI()
        return api.ask(prompt)

    return ask


def test_agent_lists_assets(llm_agent):
    prompt = "What assets are in the library?"
    ret = llm_agent(prompt)
    tools_used = [tool.lower() for tool in ret["tools"]]
    response = ret["answer"]

    # Keywords we expect to appear if the tool was called correctly
    expected_keywords = [
        "Theatre",
        "Robot",
        "Lego",
        "Astronaut",
        "Samurai",
        ".glb",
        ".webp",
        ".png",
        ".txt",
    ]

    for keyword in expected_keywords:
        assert keyword in response, f"Missing '{keyword}' in agent response"

    # Should call date tool only
    assert "list_assets" in tools_used
    assert len(tools_used) == 1
