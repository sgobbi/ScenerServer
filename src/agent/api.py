import asyncio
from agent.agent import Agent
from agent.llm.interaction import chat, achat, ask, aask
from asyncio import Queue
from beartype import beartype
from library.api import LibraryAPI
from server.data.redis import Redis

# from langchain.globals import set_debug

# set_debug(True)


@beartype
class AgentAPI:
    def __init__(
        self,
        redis_api: Redis = None,
        library_api: LibraryAPI = None,
        main_loop: asyncio.AbstractEventLoop = None,
    ):
        self.agent = Agent(redis_api, library_api, main_loop)

    def chat(self, user_input: str, thread_id: str = 0) -> str:
        chat(self.agent, user_input, thread_id)

    def achat(self, user_input: str, tool_output: Queue, thread_id: str = 0):
        return achat(self.agent, user_input, tool_output, thread_id)

    def run(self):
        self.agent.run()

    def ask(self, query: str, thread_id: str) -> dict:
        return ask(self.agent, query, thread_id)

    def aask(self, query: str, thread_id: str):
        return aask(self.agent, query, thread_id)
