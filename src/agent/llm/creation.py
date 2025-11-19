from beartype import beartype
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent


def initialize_model(model_name: str, temperature: int = 0):
    """Initialize the model from its name"""
    return ChatOllama(
        model=model_name, temperature=temperature, streaming=True, keep_alive=0
    )


@beartype
def initialize_agent(model_name: str, tools: list[BaseTool], base_prompt: str):
    """Initialize the agent with the specified tools and prompt."""
    llm = initialize_model(model_name)
    memory = InMemorySaver()

    agent = create_react_agent(
        tools=tools,
        model=llm,
        prompt=base_prompt,
        checkpointer=memory,
    )
    return agent
