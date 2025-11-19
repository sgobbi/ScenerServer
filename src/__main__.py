import library
import server

import json
import os

import utils
import library
import server
import model


if __name__ == "__main__":
    utils.init()
    library.init()
    server.start()


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "../../config.json")


def load_config():
    """Load the configuration from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file '{CONFIG_PATH}' not found.")

    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    config = load_config()
    try:
        host, port, agent_model_name = (
            config.get("host"),
            config.get("localhost"),
            config.get("agent_model_name"),
        )
    except KeyError:
        host = "localhost"
        port = 8000
    # library.init()
    server.start(host, port, agent_model_name)
