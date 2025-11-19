from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from colorama import Fore
from loguru import logger
import subprocess


@tool
def image_to_depth():
    """Compute a depth image from a color image"""

    subprocess.run(
        [
            "model/Marigold/venv/bin/python",
            "model/Marigold/script/depth/run.py",
            "--checkpoint",
            "prs-eth/marigold-depth-v1-1",
            "--input_rgb_dir",
            "model/Marigold/input/one",
            "--output_dir",
            "model/Marigold/output/one",
            "--fp16",
        ],
        check=True,
    )
