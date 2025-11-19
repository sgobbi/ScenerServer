from beartype import beartype
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from agent.llm.creation import initialize_model
from lib import load_config, logger


@beartype
def improve_prompt(user_input: str, temperature: int = 0) -> str:
    # TODO: mandatory room? if other type of background?
    try:
        system_prompt = """
                You are a specialized Prompt Engineer for 3D object generation.

                YOUR TASK:
                - Given a user's prompt for a single object, produce an improved, detailed, and clarified version of its description.
                - Focus *exclusively* on the physical aspects of the object itself.

                OUTPUT FORMAT:
                - Return ONLY the improved text string for the object.
                - NO explanations, NO preambles, NO markdown, NO extra text.

                GUIDELINES:
                - Enhance clarity, specificity, and actionable detail regarding the object's design, material, texture, color, and key visible features.
                - All details MUST refer to the physical aspects of the object. DO NOT include lighting, weather effects, or its relationship to other objects or placement in a larger scene (beyond the required background/camera statements).
                - You may infer reasonable details from the context if missing (e.g., typical materials for the object type).
                - NEVER invent unrelated storylines, characters, or scenes not implied by the original object prompt.
                - NEVER output anything other than the improved description string itself.
                - The prompt must provide a **rich, detailed description** of the object’s physical features.
                - The prompt must include:
                    - "Placed on a white and empty background."
                    - "Completely detached from surroundings."
                - **Camera view** based on object type:
                    - For non-room objects (e.g., 'prop', 'furniture', 'character'): Use "front camera view".
                    - For room objects (e.g., 'room', 'environment'): Use "squared room view from the outside with a distant 3/4 top-down perspective".

                EXAMPLE OF AN IMPROVED *OBJECT* PROMPT (for a non-room object):
                Original: "a red chair"
                Improved: "A vibrant red armchair, crafted from polished mahogany wood, featuring a high back with button-tufted detailing, plush velvet cushioning on the seat and backrest, and elegantly curved cabriole legs. Front camera view. Placed on a white and empty background. Completely detached from surroundings."

                EXAMPLE OF AN IMPROVED *ROOM* PROMPT:
                Original: "a kitchen"
                Improved: "A modern, minimalist kitchen with sleek white cabinetry, stainless steel appliances including a double-door refrigerator and a built-in oven, a central island with a quartz countertop and induction cooktop, and light gray porcelain tile flooring. Squared room view from the outside with a distant 3/4 top-down perspective. Placed on a white and empty background. Completely detached from surroundings."
                """
        user_prompt = "User: {user_input}"
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", user_prompt),
            ]
        )
        parser = StrOutputParser()

        config = load_config()
        improver_model_name = config.get("improver_model")
        model = initialize_model(improver_model_name, temperature=temperature)

        chain = prompt | model | parser

        logger.info(f"Improving user's input: {user_input}")
        result: str = chain.invoke({"user_input": user_input})
        logger.info(f"Improved result: {result}")

        return result
    except Exception as e:
        logger.error(f"Failed to improve the prompt: {e}")
        raise ValueError(f"Failed to improve the prompt: {e}")


if __name__ == "__main__":
    user_input = "a cat"
    superprompt = improve_prompt(user_input)
    print(superprompt)
