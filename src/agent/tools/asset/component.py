from colorama import Fore
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from lib import logger
from pathlib import Path


@tool
def send_component(path: str):
    """Send the requested component (an image or a mesh) of an asset to the user"""
    pass
