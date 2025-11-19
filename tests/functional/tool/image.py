from agent.api import AgentAPI
from datetime import datetime
import pytest


@pytest.fixture
def llm_agent():
    def ask(prompt: str) -> dict:
        api = AgentAPI()
        return api.ask(prompt)

    return ask


def test_agent_analyse_image(llm_agent):
    prompt = "Can you analyse the image of the asset 'Lego' ? "
    ret = llm_agent(prompt)
    tools_used = [tool.lower() for tool in ret["tools"]]
    response = ret["answer"]

    assert "list_assets" in tools_used
    assert "image_analysis" in tools_used
    assert len(tools_used) == 2
