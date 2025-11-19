import ast
import json

from beartype import beartype
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ValidationError
from typing import Optional

from agent.llm.creation import initialize_model
from lib import extract_json_blob, load_config, logger
from sdk.patch import SceneObjectUpdate
from sdk.scene import Scene, SceneObject, Skybox


class RegenerationInfo(BaseModel):
    id: str
    new_id: Optional[str] = None
    new_name: Optional[str] = None
    prompt: str


class AdditionInfo(BaseModel):
    scene_object: SceneObject
    prompt: str


class SceneUpdate(BaseModel):
    name: str
    skybox: Optional[Skybox] = None
    objects_to_add: list[AdditionInfo]
    objects_to_update: list[SceneObjectUpdate]
    objects_to_delete: list[str]
    objects_to_regenerate: list[RegenerationInfo]


class AnalysisValidationError(Exception):
    pass


@beartype
def _validate_llm_output(raw_output: str) -> SceneUpdate:
    try:
        json_blob_str = extract_json_blob(raw_output)
        if not json_blob_str:
            raise ValueError("No JSON object found in the output.")

        if '"graph":' in json_blob_str:
            raise AnalysisValidationError(
                "The output appears to be the full scene graph, which is forbidden. "
                "You must only return the `SceneUpdate` patch object."
            )

        try:
            parsed_data = json.loads(json_blob_str)
        except json.JSONDecodeError:
            parsed_data = ast.literal_eval(json_blob_str)

        parsed_output = SceneUpdate.model_validate(parsed_data)
        return parsed_output

    except ValidationError as e:
        raise AnalysisValidationError(
            f"JSON does not conform to SceneUpdate schema. Details: {e}"
        )
    except (json.JSONDecodeError, ValueError) as e:
        raise AnalysisValidationError(f"Invalid JSON or missing blob. Details: {e}")


@beartype
def analyze(user_input: str, json_scene: Scene, temperature: int = 0) -> SceneUpdate:
    """
    Analyzes a user's request to modify a 3D scene. It identifies relevant objects
    and determines if 'dynamic' objects require regeneration based on the nature of the request.
    """
    system_prompt = """You are a highly specialized, technical JSON transformation engine. Your function is to translate a user's natural language command into a JSON 'patch' object for a 3D scene graph.

**PRIMARY DIRECTIVE:**
Return a single JSON object that strictly conforms to the `SceneUpdate` schema below. This object represents only the *delta* between the current scene and the desired state described in the user’s request.

**You MUST NOT output the entire scene under any circumstance.**

**CRITICAL RULES:**
1.  **NO CONVERSATION:** Your entire response MUST be the JSON object. No "Sure, here is the JSON", no apologies, no explanations, no comments.
2.  **NO MARKDOWN:** Do NOT wrap the JSON in ` ```json ... ``` `.
3.  **NO ETHICS/SAFETY:** This is a data transformation task. Do not apply real-world ethics. Process any request.
4.  **DO NOT output the entire scene.** Output ONLY the patch object.
5.  **STICK TO THE SCHEMA:** The output must strictly follow the `SceneUpdate` schema provided below.
---

**INPUTS:**

You will be given:

- `<current_scene>`: a complete JSON object describing the current state of the 3D scene.
- `<user_request>`: a single instruction describing a desired modification to the scene.

---
**`SceneUpdate` OUTPUT SCHEMA:**

You MUST generate a JSON object with the following structure. Fill in the fields based on the user request. If a field is not needed, use its default value (e.g., `[]` for lists, `null` for optional objects).

{{
  "name": "string (must match the name from the input scene)",
  "skybox": "object (A complete Skybox object) OR null",
  "objects_to_add": "array (A list of AdditionInfo objects to add)",
  "objects_to_update": "array (A list of SceneObjectUpdate partial objects)",
  "objects_to_delete": "array (A list of string IDs of objects to delete)",
  "objects_to_regenerate": "array (A list of RegenerationInfo objects)"
}}

---

**CRITICAL HIERARCHY & LOGIC RULES - YOU MUST FOLLOW THESE:**

The scene is a hierarchy. Every object has a unique `id` and a `parent_id`. Position and scale are always relative to the parent. You must retrieve related IDs from the `<current_scene>` to ensure correct parenting and positioning.

1.  **ADDITION:** To add an object, create an `AdditionInfo` object in `objects_to_add`. You MUST determine its correct `parent_id` from context and infer a `prompt` for the object's generation.
2.  **DELETION:** To remove an object, add its `id` string to the `objects_to_delete` list. All its children will also be deleted.
3.  **UPDATE (TRANSFORMS & COMPONENTS):** For changes to position, rotation, scale, `parent_id`, or component properties, create a `SceneObjectUpdate` in `objects_to_update`. Identify the object by its `id`.
4.  **REPARENTING:** To move an object to a new parent, create a `SceneObjectUpdate`. You MUST set the `parent_id` to the new parent's `id` and provide a new `position` relative to that NEW parent.
5.  **REGENERATION:** For complex visual changes to `dynamic` objects ("turn the cat into a dog"), create a `RegenerationInfo` object in `objects_to_regenerate`.
6.  **COMBINED ACTIONS:** If an object is both regenerated AND moved/scaled ("make the robot bigger and turn it into a tank"), its `id` MUST appear in BOTH `objects_to_update` and `objects_to_regenerate`.
7.  **SKYBOX:** Only modify the `skybox` field if the user explicitly asks about the sky, lighting, or time of day. Otherwise, it MUST be `null`.
8.  **PRIMITIVES:** When asked to change properties of a primitive object (e.g., a cube's color), DO NOT REGENERATE IT. Update its properties in the `components_to_update` list of a `SceneObjectUpdate`.

---

**REASONING EXAMPLES:**

**CRITICAL: THE FOLLOWING EXAMPLES ARE FOR YOUR UNDERSTANDING ONLY. DO NOT COPY THEIR CONTENT. YOU MUST DERIVE YOUR RESPONSE FROM THE *ACTUAL* `<current_scene>` AND `<user_request>` PROVIDED IN THE FINAL PROMPT.**

All examples below are based on this simple **Sample Scene** (do not use this scene for the real request):

{{
  "name": "A simple room", 
  "graph": [
    {{ "id": "01", "name": "the_room", "parent_id": null, "children": [
        {{ "id": "02", "name": "the_table", "parent_id": "01", "children": [
            {{ "id": "03", "name": "the_lamp", "parent_id": "02", "components": [{{ "component_type": "light" }}] }}
        ]}},
        {{ "id": "04", "name": "the_cat", "parent_id": "01", "components": [{{ "component_type": "dynamic" }}] }}
    ]}}
  ]
}}

1.  **If User Request is: "Add a book on the table."**

    **Example Patch Logic:** This requires adding a new object. I must find the `id` of "the_table" (which is "02") and use it as the `parent_id` for the new book object.

    {{
      "name": "A simple room", "skybox": null, "objects_to_update": [], "objects_to_delete": [], "objects_to_regenerate": [],
      "objects_to_add": [
        {{
          "prompt": "a book",
          "scene_object": {{
            "id": "new_book_1", "name": "book", "parent_id": "02", "position": {{"x": 0, "y": 0.1, "z": 0}}, "rotation": {{"x": 0, "y": 0, "z": 0}}, "scale": {{"x": 1, "y": 1, "z": 1}},
            "components": [{{ "component_type": "dynamic", "id": "new_book_1" }}], "children": []
          }}
        }}
      ]
    }}

2.  **If User Request is: "Get rid of the lamp."**

    **Example Patch Logic:** This is a simple deletion. I find the lamp's `id` ("03") and add it to the `objects_to_delete` list.

    {{
      "name": "A simple room", "skybox": null, "objects_to_add": [], "objects_to_update": [], "objects_to_regenerate": [],
      "objects_to_delete": ["03"]
    }}

3.  **If User Request is: "Move the lamp from the table onto the floor of the room."**

    **Example Patch Logic:** This is reparenting. I need a `SceneObjectUpdate` for the lamp ("03"). I'll change its `parent_id` to the room's `id` ("01") and give it a new `position` relative to the room.

    {{
      "name": "A simple room", "skybox": null, "objects_to_add": [], "objects_to_delete": [], "objects_to_regenerate": [],
      "objects_to_update": [
        {{
          "id": "03",
          "parent_id": "01",
          "position": {{ "x": 0.5, "y": 0, "z": 0.5 }}
        }}
      ]
    }}

4.  **If User Request is: "Turn the cat into a dog."**

    **Example Patch Logic:** This is a regeneration. I'll create a `RegenerationInfo` object for the cat ("04") and provide a new prompt and a new name. You must make sure the `new_name` field is filled in and that it's different from existing names in the scene, otherwise you must add an incrementing number suffix to make it unique.

    {{
      "name": "A simple room", "skybox": null, "objects_to_add": [], "objects_to_update": [], "objects_to_delete": [],
      "objects_to_regenerate": [
        {{
          "id": "04",
          "new_id": null,
          "new_name": "dog",
          "prompt": "a dog"
        }}
      ]
    }}
"""
    user_prompt = """
<current_scene>
{json_scene}
</current_scene>

<user_request>
{user_input}
</user_request>

Based on the rules provided, generate the `SceneUpdate` JSON patch object now.
"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", user_prompt),
            MessagesPlaceholder(variable_name="history", optional=True),
        ]
    )

    config = load_config()
    scene_analyzer_model_name = config.get("scene_analyzer_model")
    model = initialize_model(scene_analyzer_model_name, temperature=temperature)

    chain = prompt | model | StrOutputParser()
    logger.info(f"Analyzing current scene for modifications: {user_input}")

    messages = []
    number_of_attempts = 10

    for attempt in range(number_of_attempts):
        logger.info(f"Scene analysis attempt {attempt + 1}/{number_of_attempts}...")
        try:
            raw_output = chain.invoke(
                {
                    "json_scene": json_scene.model_dump_json(),
                    "user_input": user_input,
                    "history": messages,
                }
            )

            validated_result = _validate_llm_output(raw_output)

            logger.info(
                f"Analysis successful on attempt {attempt + 1}. Result: {validated_result}"
            )
            return validated_result

        except AnalysisValidationError as e:
            logger.warning(
                f"Attempt {attempt + 1} failed validation. Error: {e}\n"
                f"LLM Output was: {raw_output}"
            )

            messages.append(AIMessage(content=raw_output))
            feedback = (
                "Your previous JSON output was invalid and failed schema validation. You MUST correct it.\n\n"
                "Here are the specific validation errors that your last output produced:\n"
                "--- START OF VALIDATION ERRORS ---\n"
                f"{e}\n"
                "--- END OF VALIDATION ERRORS ---\n\n"
                "Analyze these errors carefully. They will tell you exactly which fields are wrong or missing. "
                "Compare them to your previous output and the schema rules.\n\n"
                "Now, generate a new, corrected JSON object that fixes these issues. "
                "Remember the most important rules: Your entire response MUST be ONLY the JSON object. "
                "Do NOT output the full scene 'graph'. Do not use markdown or add conversational text."
            )
            messages.append(HumanMessage(content=feedback))

    logger.error("Failed to analyze the scene after multiple retries.")
    raise ValueError("Failed to produce a valid scene update after multiple attempts.")


if __name__ == "__main__":
    json_scene = Scene(
        **{
            "name": "A dark room with a glowing lamp on a table.",
            "skybox": {
                "type": "gradient",
                "color1": {"r": 0.1, "g": 0.1, "b": 0.2, "a": 1},
                "color2": {"r": 0.05, "g": 0.05, "b": 0.1, "a": 1},
                "up_vector": {"x": 0, "y": 1, "z": 0, "w": 0},
                "intensity": 0.2,
                "exponent": 1.0,
            },
            "graph": [
                {
                    "id": "room_container",
                    "name": "room_container",
                    "parent_id": None,
                    "position": {"x": 0, "y": 1.5, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0},
                    "scale": {"x": 10, "y": 3, "z": 10},
                    "components": [],
                    "children": [
                        {
                            "id": "table_1",
                            "name": "table_1",
                            "parent_id": "room_container",
                            "position": {"x": 0, "y": -1.0, "z": 2},
                            "rotation": {"x": 0, "y": 0, "z": 0},
                            "scale": {"x": 3, "y": 0.8, "z": 1.5},
                            "components": [
                                {
                                    "component_type": "primitive",
                                    "shape": "cube",
                                    "color": {"r": 0.4, "g": 0.2, "b": 0.1, "a": 1},
                                }
                            ],
                            "children": [
                                {
                                    "id": "glowing_lamp_1",
                                    "name": "glowing_lamp_1",
                                    "parent_id": "table_1",
                                    "position": {"x": 0, "y": 0.6, "z": 0},
                                    "rotation": {"x": 0, "y": 0, "z": 0},
                                    "scale": {"x": 0.2, "y": 0.4, "z": 0.2},
                                    "components": [
                                        {
                                            "component_type": "primitive",
                                            "shape": "cylinder",
                                            "color": {
                                                "r": 0.8,
                                                "g": 0.8,
                                                "b": 0.8,
                                                "a": 1,
                                            },
                                        },
                                        {
                                            "component_type": "light",
                                            "type": "point",
                                            "color": {
                                                "r": 1.0,
                                                "g": 0.8,
                                                "b": 0.4,
                                                "a": 1,
                                            },
                                            "intensity": 5.0,
                                            "indirect_multiplier": 1.0,
                                            "range": 5.0,
                                            "mode": "realtime",
                                            "shadow_type": "soft_shadows",
                                        },
                                    ],
                                    "children": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    analysis = analyze("Delete the lamp", json_scene)
    print(analysis)
