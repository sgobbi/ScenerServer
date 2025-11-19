import uuid

from beartype import beartype
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from pydantic import BaseModel
from typing import Literal

from agent.llm.creation import initialize_model
from lib import extract_json_blob, load_config, logger
from sdk.scene import Scene, FinalDecompositionOutput

# TODO: pydantic field descr


class DecomposedObject(BaseModel):
    id: str
    name: str
    prompt: str
    type: Literal["primitive", "dynamic"]


class DecompositionData(BaseModel):
    objects: list[DecomposedObject]


class DecompositionOutput(BaseModel):
    scene: DecompositionData


@beartype
def initial_decomposition(user_input: str, temperature: int = 0) -> DecompositionOutput:
    system_prompt = """
You are a highly specialized and precise Scene Decomposer for a 3D rendering workflow. Your sole task is to accurately convert a scene description string into structured JSON, adhering to strict rules. The output must always extract **verbatim zero-shot prompts** for each object in the scene, following the format provided below.

YOUR CRITICAL TASK:
- Decompose the scene description into several distinct elements, ensuring at least one 'room' object.
- **Classify each object's creation type as either "dynamic" or "primitive" based on the rules below.**
- Convert the scene into a valid JSON object.
- Focus ONLY on **key physical elements**. **Do NOT extract minor details** or interpret the scene beyond identifying these key elements.
- **The most critical part of the output is the 'prompt' field for each object.** This field must contain the **exact, verbatim phrase** describing that specific object as it appeared in the user's input scene description. **Do NOT modify, enhance, or add ANY details (like camera angles, background information, or context) to this user-provided object description.**
- If there are words like "on", "in", "under", "next to", "beside", "above", "below", etc., do NOT include them in the 'prompt' field. The 'prompt' must be the exact noun phrase or descriptive phrase that identifies or describes the object itself.
- If there are words like "few", "several", "many", "couple of", etc., you must create one object entry for each individual item described. For example, "a couple of chairs" means you must create two separate objects with identical prompts.

### OBJECT CLASSIFICATION: THE CORE TASK
  **STEP 1: Identify the Environment/Container Object (Highest Priority Rule).**
  - First, find the object that defines the scene's main space. This could be "a room", "a hall", "a cave", "an outdoor area", etc.
  - These large-scale container objects, which represent the overall environment, are **ALWAYS `primitive`**.
  - **This rule is an exception and overrides all others.** Even though "a room" is a named concept, for our purposes, it is the primitive cube that holds all other objects.
  - **Examples:** `"a sunny room"`, `"a cozy living room"`, `"a dark cave"`, `"a large hall"`. All of these container objects must be classified as **`primitive`**.

  **STEP 2: Classify All Other Objects (Props and Furniture).**
  - For every other object that exists *inside* the container, apply the following test:
    > "Is this a specific, named, real-world object (like a 'chair', 'lamp', or 'cat') OR is it just a generic geometric building block (like 'a cube' or 'a plane')?"

  - **Use `"dynamic"` for ANY named prop or furniture.** This applies even if its shape seems simple. If it has a common name and function, it is dynamic.
    - **Examples:** "a table", "a chair", "a chandelier", "a chimney", "a lamp", "a cat", "a sword", "a coffee mug". All of these are **`dynamic`**.

  - **Use `"primitive"` ONLY for basic, unnamed geometric shapes** that are NOT the main room container.
    - **Examples:** "a large cube used as a pedestal", "a sphere on the floor", "a flat plane".

OUTPUT FORMAT:
- Output **ONLY** the JSON. **NO explanations**, **NO markdown**, **NO extra formatting**.

JSON STRUCTURE (STRICT AND REQUIRED):
{{
  "scene": {{
    "objects": [
      {{
        "id": "unique_object_id" // must be str
        "name": "concise_descriptive_object_name",  // short, clear identifier (e.g., 'black_cat', 'wooden_table')
        "prompt": "The exact, verbatim phrase describing this specific object, extracted directly from the user's input scene description. This must be the exact noun phrase or descriptive phrase from the input that **identifies or describes the object itself**. **Do NOT include prepositions (like 'on', 'in', 'under'), verbs describing actions, or phrases indicating relationships to other objects.** Do NOT modify capitalization. For example, if the user input mentions 'a fluffy white dog', this prompt should be exactly 'a fluffy white dog'. If the input is 'cat on a table', the prompt for the cat is 'cat' and the prompt for the table is 'a table' (or just 'table' depending on the exact wording around it)."
        "type": "dynamic" // MUST be either "dynamic" or "primitive"
      }},
      // Add one entry per main object. STRICTLY follow this format.
    ]
  }}
}}

RULES FOR OBJECT SELECTION:
1. IDENTIFY MAIN OBJECTS ONLY:
   - Must be clearly described, physical, and significant in the scene.
   - Examples: cat → prop, couch → furniture, gothic library → room.

2. A **room object is always required**. If the scene description implies an outdoor setting without a defined room, you may need to infer a generic 'outdoor_space' or similar as the 'room' type object, and its prompt would be the relevant part of the user's description for that space.

3. STRICTLY EXCLUDE:
   - Lights, shadows, ambient/sunlight.
   - Fog, mist, atmosphere, dust.
   - Generic walls/floor/ceiling unless the room is the focused element and described as such.
   - Minor clutter (utensils, cushions, books) unless explicitly emphasized as a main object.

4. DEFAULT FIELD VALUES:
   - For 'name', use inferred or standard value if not explicitly detailed for the object in the user's prompt. The 'prompt' field, however, must remain verbatim.

STRICT ADHERENCE TO THIS FORMAT AND OBJECT INCLUSION IS ESSENTIAL FOR SUCCESSFUL RENDERING. Ensure all main physical objects described and the required room object are included. The 'prompt' field must be the exact, verbatim text from the input that *identifies or describes* that specific object, not its relationship to others.
"""
    user_prompt = "User: {user_input}"
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", user_prompt),
        ]
    )

    parser = JsonOutputParser(pydantic_object=DecompositionOutput)

    prompt_with_instructions = prompt.partial(
        format_instructions=parser.get_format_instructions()
    )

    config = load_config()
    initial_decomposer_model_name = config.get("initial_decomposer_model")

    model = initialize_model(initial_decomposer_model_name, temperature=temperature)

    chain = prompt_with_instructions | model.with_structured_output(
        schema=DecompositionOutput
    )

    try:
        logger.info(f"Decomposing input: {user_input}")
        result: DecompositionOutput = chain.invoke({"user_input": user_input})

        # validated_result = DecompositionOutput(**result)

        # Not relying on the llm to provide unique id for every object
        for obj_dict in result.scene.objects:
            obj_dict.id = str(uuid.uuid4())

        logger.info(f"Decomposition result: {result}")

        return result
    except Exception as e:
        logger.error(f"Failed to do initial decomposition: {str(e)}")
        raise


@beartype
def final_decomposition(
    user_input: str,
    improved_decomposition: DecompositionOutput,
    temperature: int = 0,
) -> FinalDecompositionOutput:
    system_prompt = """
You are a world-class 3D scene architect AI. Your primary function is to interpret a user's description and translate it into a highly structured, hierarchical 3D scene in a strict JSON format. Your ability to correctly infer relationships between objects (like containment and relative scale) is paramount.

Your ONLY task is to create this JSON. Your entire response MUST be only the JSON object.

### 1. CRITICAL OUTPUT STRUCTURE (HIGHEST PRIORITY)
Your output MUST be a single JSON object.
The root of this JSON object MUST have exactly three keys: `name`, `skybox`, and `graph`.
Do NOT wrap your output in a `scene` key or any other key.

### 2. SKYBOX GENERATION - CRITICAL INSTRUCTIONS
You MUST generate a complete `skybox` object if necessary. Analyze the user's prompt for ambiance clues ("sunny day", "night", "dusk").

- **If the scene is outdoors or sunlit (e.g., "a sunny room"), you MUST use the `sun` type skybox.** When you use type `sun`, you are REQUIRED to include ALL of its fields: `type`, `top_color`, `top_exponent` (a real number), `horizon_color`, `bottom_color`, `bottom_exponent` (a real number), `sun_color`, `sky_intensity`, `sun_intensity`, `sun_alpha`, `sun_beta`, and especially the `sun_vector` object with `x`, `y`, `z`, and `w` fields.
- **If the scene is a dark interior or has abstract lighting, you MUST use the `gradient` type skybox.** When you use type `gradient`, you are REQUIRED to include ALL of its fields: `type`, `color1`, `color2`, `up_vector`, `intensity`, `exponent`.
- You MUST also add a `directional` light to the scene graph to act as the sun when using a `sun` skybox.

CORE SCENE-BUILDING LOGIC - YOU MUST FOLLOW THIS PROCESS:

    **1. The Container Principle (Most Important Rule): Your absolute first priority is to establish a logical parent-child hierarchy. Do not create a flat list of objects.**

        - Identify the Main Container: First, find the largest, outermost object that contains others (e.g., "a room", "a forest", "a box", "a street"). This will be your top-level object in the graph.

        - Place Objects Inside: For every other object mentioned, determine its parent. A "cat in a room" means the cat object is a child of the room object. A "lamp on a desk" means the lamp is a child of the desk.

    **2. Relative Coordinates & Relative Scale: This is critical for making the hierarchy work.**

        - A child object's position MUST be relative to its parent's center. For an object on the floor of a room, its y position will be negative (relative to the room's center). For an object on a table, its y position will be positive (relative to the table's center).

        - A child's scale MUST be proportionally smaller than its parent. A cat cannot be the same size as the room it is in. A lamp is much smaller than a desk.

    **3. Set Global and Local Lighting (The Illumination Principle):**
        - This is a mandatory step for every scene.
        - Step A: Global Light (Skybox and Sun): First, analyze the user's prompt for ambiance clues ("sunny day", "nighttime", "dusk", "overcast").
            - For outdoor or bright indoor scenes (e.g., "a sunlit kitchen"), you MUST use a `sun` type skybox and you MUST also add a `directional` light to the scene graph to act as the sun. The rotation of this directional light should correspond to the sun's direction.
            - For moody, abstract, or simple indoor scenes (e.g., "a dark room"), a `gradient` or `cubed` skybox is appropriate. A directional light is not required in this case unless specified.
        - Step B: Local Lights (Point, Spot, Area): Second, add artificial lights where logically necessary.
            - If the scene is an enclosed space (like a room, cave, or hallway) and it's not described as brightly sunlit, you MUST add at least one `point` or `spot` light to illuminate the interior.
            - If the user explicitly mentions a light source (e.g., "a desk lamp", "a glowing crystal", "a street light"), you MUST create a `SceneObject` for that item (e.g., a primitive cylinder for the lamp base) AND add a `light` component to it. The light component should be positioned at the source of illumination (e.g., at the bulb of the lamp).

    **4. Use Common Sense: Apply real-world logic. Objects rest on surfaces, not inside them. Infer reasonable sizes, positions, and colors if not specified. A floor is a large, flat plane at the bottom of a room.**

SCHEMA REFERENCE - YOU MUST FOLLOW THIS STRICTLY

    **1. "graph" (The Scene Hierarchy):**

        - The graph is a list of SceneObject nodes, which are the top-level objects in the scene.

        - Each SceneObject represents a container and MUST have these fields: id, name, parent_id, position, rotation, scale, components, and children. Name should be a short, descriptive identifier (e.g., "cat", "wooden_table", "sunlit_kitchen").

        - The children field is a list of other SceneObject nodes; **IMPORTANT**: it is ALWAYS present in the structure, and if a SceneObject logically has no children, it MUST BE an empty list [].

        - You must infer the relationships between objects based on the scene description. For example, if a lamp is inside a box, the lamp must be a child of the box.

        - If a SceneObject1 is a children of SceneObject2, parent_id of SceneObject1 must be id of SceneObject2. Always keep this coherence between parent and child ids.

        - **CRITICAL ID RULE:** You MUST use the exact UUIDs provided to you in the `Decomposed Objects` input. Do NOT invent new IDs or use simplified numbers like "1", "2", "3". The `parent_id` of a child object MUST exactly match the `id` of its parent from the provided list.
    
    **2. "components" (Defining what a SceneObject is):**

        - The components list is the most important part. Every item in it MUST have a component_type field.

            **CRITICAL RULE**: component_type MUST be one of "primitive", "dynamic", or "light". For the objects from the initial decomposition, you **MUST** use the type field from the DecomposedObject.

            - If component_type is "primitive":

                The component object MUST also contain:

                    shape: One of "cube", "sphere", "plane", "quad", "cylinder", "capsule". Those are the only valid values.

                    color: An RGBA color object.

            - If component_type is "dynamic":

                The component object MUST also contain:

                    id: EXACTLY the same id as its SceneObject (for example, if a SceneObject with id cat_1234 have a component with "dynamic" component_type, id field will be also "cat_1234").

            - If component_type is "light":

                The component object MUST also contain a type field: "directional", "point", "spot", or "area".

                All light components MUST have: color, intensity, indirect_multiplier.

                For a Directional Light, you MUST also include: mode ("baked", "mixed" or "realtime") and shadow_type ("no_shadows", "hard_shadows" or "soft_shadows").

                For a Point Light, you MUST also include: range, mode ("baked", "mixed" or "realtime"), and shadow_type ("no_shadows", "hard_shadows" or "soft_shadows").

                For a Spot Light, you MUST also include: range, spot_angle, mode ("baked", "mixed" or "realtime"), and shadow_type ("no_shadows", "hard_shadows" or "soft_shadows").

                For an Area Light, you MUST also include: range, shape ("rectangle" or "disk"), and width/height (for rectangle) or radius (for disk).

**IMPORTANT: Vectors (position, rotation, scale) have x, y, z fields.**
**IMPORTANT: Colors (color, top_color, etc.) are RGBA format (include 'r', 'g', 'b', and 'a' components).**

**CRITICAL RULES:**

    - STRICT SCHEMA: Adhere strictly to the fields and values listed in the SCHEMA REFERENCE above. Every SceneObject must have a components list, even if it's empty.
---

### DETAILED EXAMPLES - USE THESE AS YOUR BLUEPRINT

**OUTPUT EXAMPLE 1**
{{
  "name": "A red car parked on a street on a sunny day.",
  "skybox": {{
    "type": "sun",
    "top_color": {{"r": 0.3, "g": 0.5, "b": 0.8, "a": 1}}, 
    "top_exponent": 1.5, 
    "horizon_color": {{"r": 0.7, "g": 0.6, "b": 0.5, "a": 1}}, 
    "bottom_color": {{"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}}, 
    "bottom_exponent": 1.0, 
    "sun_color": {{"r": 1.0, "g": 0.95, "b": 0.8, "a": 1}}, 
    "sky_intensity": 1.0, 
    "sun_intensity": 1.5, 
    "sun_alpha": 120.0, 
    "sun_beta": 45.0, 
    "sun_vector": {{"x": 0.5, "y": 0.5, "z": 0.0, "w": 0.0
    }}
  }},
  "graph": [
    {{
      "id": "f4f4a2b0-sun-light",
      "name": "the_sun", 
      "parent_id": null, 
      "position": {{"x": 0, "y": 100, "z": 0}}, 
      "rotation": {{"x": 45, "y": 30, "z": 0}}, 
      "scale": {{"x": 1, "y": 1, "z": 1}},
      "components": [ {{ "component_type": "light", "type": "directional", "color": {{"r": 1.0, "g": 0.95, "b": 0.8, "a": 1}}, "intensity": 1.5, "indirect_multiplier": 1.0, "mode": "realtime", "shadow_type": "soft_shadows" }} ],
      "children": []
    }},
    {{
      "id": "a1b2c3d4-street-plane",
      "name": "street_plane", 
      "parent_id": null, 
      "position": {{"x": 0, "y": 0, "z": 0}}, 
      "rotation": {{"x": 0, "y": 0, "z": 0}}, 
      "scale": {{"x": 50, "y": 0.1, "z": 50}},
      "components": [ {{ "component_type": "primitive", "shape": "plane", "color": {{"r": 0.3, "g": 0.3, "b": 0.3, "a": 1}} }} ],
      "children": [
        {{
          "id": "e5f6g7h8-red-car",
          "name": "red_car",
          "parent_id": "a1b2c3d4-street-plane",
          "position": {{"x": 2, "y": 0.5, "z": 5}}, "rotation": {{"x": 0, "y": 15, "z": 0}}, "scale": {{"x": 2, "y": 1, "z": 4}},
          "components": [ {{ "component_type": "dynamic", "id": "e5f6g7h8-red-car" }} ],
          "children": []
        }}
      ]
    }}
  ]
}}

**OUTPUT EXAMPLE 2**
{{
  "name": "A dark room with a glowing lamp on a table.",
  "skybox": {{
    "type": "gradient", 
    "color1": {{"r": 0.1, "g": 0.1, "b": 0.2, "a": 1}}, 
    "color2": {{"r": 0.05, "g": 0.05, "b": 0.1, "a": 1}}, 
    "up_vector": {{"x": 0, "y": 1, "z": 0, "w": 0}}, 
    "intensity": 0.2, 
    "exponent": 1.0
  }},
  "graph": [
    {{
      "id": "uuid-for-room-container",
      "name": "room_container", 
      "parent_id": null, 
      "position": {{"x": 0, "y": 1.5, "z": 0}}, 
      "rotation": {{"x": 0, "y": 0, "z": 0}}, 
      "scale": {{"x": 10, "y": 3, "z": 10}},
      "components": [],
      "children": [
        {{
          "id": "uuid-for-wooden-table",
          "name": "wooden_table",
          "parent_id": "uuid-for-room-container",
          "position": {{"x": 0, "y": -1.0, "z": 2}}, 
          "rotation": {{"x": 0, "y": 0, "z": 0}}, 
          "scale": {{"x": 3, "y": 0.8, "z": 1.5}},
          "components": [ {{ "component_type": "primitive", "shape": "cube", "color": {{"r": 0.4, "g": 0.2, "b": 0.1, "a": 1}} }} ],
          "children": [
            {{
              "id": "uuid-for-glowing-lamp",
              "name": "glowing_lamp",
              "parent_id": "uuid-for-wooden-table",
              "position": {{"x": 0, "y": 0.6, "z": 0}}, 
              "rotation": {{"x": 0, "y": 0, "z": 0}}, 
              "scale": {{"x": 0.2, "y": 0.4, "z": 0.2}},
              "components": [
                {{ "component_type": "primitive", "shape": "cylinder", "color": {{"r": 0.8, "g": 0.8, "b": 0.8, "a": 1}} }},
                {{ "component_type": "light", "type": "point", "color": {{"r": 1.0, "g": 0.8, "b": 0.4, "a": 1}}, "intensity": 5.0, "indirect_multiplier": 1.0, "range": 5.0, "mode": "realtime", "shadow_type": "soft_shadows" }}
              ],
              "children": []
            }}
          ]
        }}
      ]
    }}
  ]
}}

---
### FINAL CHECK
Remember, your entire output must be one JSON object  `{{"name": ..., "skybox":..., "graph":...}}`. Do not add any other wrappers.
"""
    user_prompt = """
<INPUT_DATA>
    <ORIGINAL_REQUEST>
    {user_input}
    </ORIGINAL_REQUEST>

    <OBJECT_LIST>
    {improved_decomposition}
    </OBJECT_LIST>
</INPUT_DATA>

<YOUR_TASK>
Using the data provided in `<INPUT_DATA>`, generate the complete 3D scene JSON.
Your output must be a single JSON object with the root keys `name`, `skybox`, and `graph`, as specified in your system instructions.
Do NOT copy the structure from `<OBJECT_LIST>`. That is input data only. You must keep the `id` and `type` values from `<OBJECT_LIST>` exactly as they are for each object.
</YOUR_TASK>
"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", user_prompt),
        ]
    )

    parser = JsonOutputParser(pydantic_object=Scene)

    prompt_with_instructions = prompt.partial(
        format_instructions=parser.get_format_instructions()
    )

    config = load_config()
    final_decomposer_model_name = config.get("final_decomposer_model")

    model = initialize_model(final_decomposer_model_name, temperature=temperature)

    chain = (
        prompt_with_instructions
        | model
        | StrOutputParser()
        | RunnableLambda(extract_json_blob)
        | parser
    )

    try:
        logger.info(
            f"Final decomposition with input: original_prompt='{user_input}', improved_decomposition: {improved_decomposition.scene}."
        )
        result: Scene = Scene(
            **chain.invoke(
                {
                    "user_input": user_input,
                    "improved_decomposition": improved_decomposition,
                }
            )
        )

        for obj in result.graph:
            obj.id = str(uuid.uuid4())
        logger.info(f"Decomposition result: {result}")

        return FinalDecompositionOutput(
            scene=result,
        )

    except Exception as e:
        logger.error(f"Failed to do the final decomposition: {str(e)}")
        raise


if __name__ == "__main__":
    # decomposer = initial_decomposition("llama3.1")
    # user_input = "A plush, cream-colored couch with a low back and rolled arms sits against a wall in a cozy living room. A sleek, gray cat with bright green eyes is curled up in the center of the couch, its fur fluffed out slightly as it sleeps, surrounded by a few scattered cushions and a worn throw blanket in a soft blue pattern."
    # output = initial_decomposition(user_input, "llama3.1")
    # print(output)

    improved_decomposition = DecompositionOutput(
        **{
            "scene": {
                "objects": [
                    {
                        "id": "1",
                        "name": "cup_of_coffee",
                        "prompt": "a cup of coffee",
                        "type": "dynamic",
                    },
                    {
                        "id": "2",
                        "name": "wooden_table",
                        "prompt": "a wooden table",
                        "type": "primitive",
                    },
                    {
                        "id": "3",
                        "name": "sunlit_kitchen",
                        "prompt": "a sunlit kitchen",
                        "type": "primitive",
                    },
                ]
            }
        },
    )
    user_input = "A cup of coffee on a wooden table in a sunlit kitchen"

    output = final_decomposition(user_input, improved_decomposition)
    print(output)
