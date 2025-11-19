import json
import os
import sys
import torch

from colorama import Fore
from loguru import logger
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

from sdk.scene import Scene

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def extract_json_blob(raw_response: str) -> str:
    """
    Extracts the first JSON blob from a string that might contain other text.
    """
    start_index = raw_response.find("{")
    end_index = raw_response.rfind("}")

    if start_index != -1 and end_index != -1 and end_index > start_index:
        json_str = raw_response[start_index : end_index + 1]
        return json_str
    else:
        return raw_response


def load_config():
    """Load the configuration from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file '{CONFIG_PATH}' not found.")

    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan> | {message}",
    backtrace=True,
)


def speech_to_text(path: str) -> str:
    """Convert a vocal speech to text."""
    logger.info(
        f"{Fore.YELLOW}Speech to text conversion started for file: {path}{Fore.RESET}"
    )

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    model_id = "openai/whisper-large-v3-turbo"

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, dtype=dtype, low_cpu_mem_usage=True, use_safetensors=True
    )
    model.to(device)

    processor = AutoProcessor.from_pretrained(model_id)

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
    )

    result = pipe(path, return_timestamps=True)

    logger.info(
        f"{Fore.GREEN}Speech to text conversion completed: {result['text']}{Fore.RESET}"
    )

    return result["text"]


def deserialize_scene_json(scene_json: str) -> Scene:
    """Deserialize a JSON scene description into a Scene object."""
    try:
        scene_data = json.loads(scene_json)
        scene = Scene(**scene_data)
        logger.info(f"Scene deserialized successfully: {scene}")
        return scene
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        raise ValueError("Invalid JSON format for scene data.")
    except Exception as e:
        logger.error(f"Error deserializing scene: {e}")
        raise ValueError("Failed to deserialize scene data.")


def serialize_scene(scene: Scene) -> str:
    """Serialize a Scene object into a JSON string."""
    try:
        scene_json = scene.model_dump_json()
        logger.info(f"Scene serialized successfully: {scene_json}")
        return scene_json
    except Exception as e:
        logger.error(f"Error serializing scene: {e}")
        raise ValueError("Failed to serialize scene data.")


if __name__ == "__main__":
    scene_dict = {
        "name": "main_scene",
        "skybox": {
            "top_color": {"r": 0.199999958, "g": 0.399999976, "b": 0.8, "a": 1.0},
            "top_exponent": 1.0,
            "horizon_color": {"r": 0.9, "g": 0.8, "b": 0.6, "a": 1.0},
            "bottom_color": {
                "r": 0.299999982,
                "g": 0.299999982,
                "b": 0.349999964,
                "a": 1.0,
            },
            "bottom_exponent": 1.0,
            "sky_intensity": 1.2,
            "sun_color": {"r": 1.0, "g": 0.9, "b": 0.8, "a": 1.0},
            "sun_intensity": 1.5,
            "sun_alpha": 20.0,
            "sun_beta": 20.0,
            "sun_vector": {"x": 0.5, "y": 0.5, "z": 0.0, "w": 0.0},
            "type": "sun",
        },
        "graph": [
            {
                "id": "light1",
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"x": 50.00001, "y": 330.0, "z": -1.328236e-06},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "components": [
                    {
                        "mode": "realtime",
                        "shadow_type": "soft_shadows",
                        "color": {"r": 1.0, "g": 0.95, "b": 0.85, "a": 1.0},
                        "intensity": 1.1,
                        "indirect_multiplier": 1.0,
                        "component_type": "light",
                        "type": "directional",
                    }
                ],
                "children": [],
            },
            {
                "id": "light2",
                "position": {"x": 5.0, "y": 2.0, "z": 3.0},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                "components": [
                    {
                        "range": 15.0,
                        "mode": "mixed",
                        "shadow_type": "hard_shadows",
                        "color": {"r": 1.0, "g": 0.5, "b": 0.2, "a": 1.0},
                        "intensity": 2.5,
                        "indirect_multiplier": 1.0,
                        "component_type": "light",
                        "type": "point",
                    }
                ],
                "children": [],
            },
            {
                "id": "obj1",
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "scale": {"x": 10.0, "y": 1.0, "z": 10.0},
                "components": [
                    {
                        "shape": "plane",
                        "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0},
                        "component_type": "primitive",
                    }
                ],
                "children": [],
            },
            {
                "id": "obj2",
                "position": {"x": 0.0, "y": 1.0, "z": 5.0},
                "rotation": {"x": 0.0, "y": 24.9999981, "z": 0.0},
                "scale": {"x": 2.0, "y": 2.0, "z": 2.0},
                "components": [
                    {
                        "shape": "cube",
                        "color": {"r": 0.8, "g": 0.09999997, "b": 0.09999997, "a": 1.0},
                        "component_type": "primitive",
                    }
                ],
                "children": [],
            },
            {
                "id": "theatre",
                "position": {"x": -5.0, "y": 0.0, "z": 10.0},
                "rotation": {"x": 0.0, "y": 180.0, "z": 0.0},
                "scale": {"x": 5.0, "y": 5.0, "z": 5.0},
                "components": [{"id": "theatre", "component_type": "dynamic"}],
                "children": [],
            },
        ],
    }

    scene_json = json.dumps(scene_dict)
    deser = deserialize_scene_json(scene_json)
    ser = serialize_scene(deser)

    print(f"Deserialized scene: {deser}")
    print(f"Serialized scene: {ser}")
