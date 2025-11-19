import os
import sqlite3
import json

from beartype import beartype
from colorama import Fore
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.documents import Document
from loguru import logger
from pydantic import BaseModel, Field
from typing import Optional

from agent.llm.creation import initialize_model
from library.sql.row import SQL
from library.manager.database import Database as DB


class AppAsset(BaseModel):
    id: str
    name: str
    image: str
    mesh: str
    description: str


class NullableAppAsset(BaseModel):
    data: Optional[AppAsset] = Field(None)


@beartype
class Library:
    def __init__(self, db: DB):
        self.db = db

    def fill(self, path: str):
        """Fill the database with assets from the specified directory."""
        try:
            cursor = self.db._get_cursor()  # fresh cursor
        except Exception as e:
            logger.error(f"Failed to get a connection or cursor: {e}")
            raise

        if not os.path.exists(path):
            logger.error(f"Path to fill from does not exists: {path}")
            raise FileNotFoundError(f"Path to fill from does not exists: {path}")
        if not os.path.isdir(path):
            logger.error(f"Path to fill from is not a directory: {path}")
            raise NotADirectoryError(f"Path to fill from is not a directory: {path}")

        try:
            subfolder_names = os.listdir(path)
        except OSError as e:
            logger.error(f"Failed to list directory {path}: {e}")
            raise

        for subfolder_name in subfolder_names:
            subpath = os.path.join(path, subfolder_name)
            if os.path.isdir(subpath):
                image = mesh = description = None
                try:
                    for file_name in os.listdir(subpath):
                        file_path = os.path.join(subpath, file_name)
                        absolute_file_path = os.path.abspath(file_path)

                        if file_name.lower().endswith(
                            (".png", ".jpg", ".jpeg", ".webp")
                        ):
                            image = absolute_file_path
                        elif file_name.lower().endswith(
                            (".obj", ".fbx", ".stl", ".ply", ".glb")
                        ):
                            mesh = absolute_file_path
                        elif file_name.lower().endswith(".txt"):
                            description = absolute_file_path
                    SQL.insert_asset(
                        self.db._conn, cursor, subfolder_name, image, mesh, description
                    )
                    logger.info(
                        f"Inserted asset: {Fore.GREEN}{subfolder_name}{Fore.RESET}"
                    )
                except OSError as e:
                    logger.error(f"Failed to list subdirectory {subpath}: {e}")
                except sqlite3.Error as e:
                    logger.error(f"Failed to insert asset {subfolder_name}: {e}")

    def read(self):
        """Print out all the assets in the database."""
        # Get fresh connection and cursor for querying assets
        try:
            cursor = self.db._get_cursor()
            assets = SQL.query_assets(cursor)
            if assets:
                print(
                    f"{'ID':<4} {'Name':<10} {'Image':<10} {'Mesh':<10} {'Description':<10}"
                )
                for asset in assets:
                    asset_id, asset_name, asset_image, asset_mesh, asset_description = (
                        asset
                    )
                    name = f"{Fore.YELLOW}{asset_name:<10}{Fore.RESET}"
                    img = (
                        f"{Fore.GREEN}{'ok':<10}{Fore.RESET}"
                        if asset_image
                        else f"{Fore.RED}{'None':<10}{Fore.RESET}"
                    )
                    mesh = (
                        f"{Fore.GREEN}{'ok':<10}{Fore.RESET}"
                        if asset_mesh
                        else f"{Fore.RED}{'None':<10}{Fore.RESET}"
                    )
                    desc = (
                        f"{Fore.GREEN}{'ok':<10}{Fore.RESET}"
                        if asset_description
                        else f"{Fore.RED}{'None':<10}{Fore.RESET}"
                    )
                    print(f"{asset_id:<4} {name} {img} {mesh} {desc}")
            else:
                print("No assets found.")
        except Exception as e:
            logger.error(f"Failed to read assets from the database: {e}")
            raise

    def get_list(self):
        """Return a list of all assets as dictionaries."""
        # Get fresh connection and cursor for querying assets
        try:
            cursor = self.db._get_cursor()
            assets = SQL.query_assets(cursor)
            return [
                AppAsset(
                    id=str(asset_id),
                    name=name,
                    image=image,
                    mesh=mesh,
                    description=description,
                )
                for asset_id, name, image, mesh, description in assets
            ]
        except Exception as e:
            logger.error(f"Failed to read assets from the database: {e}")
            raise

    def get_asset(self, name: str):
        """Return asset by its name"""
        try:
            cursor = self.db._get_cursor()
            asset = SQL.query_asset_by_name(cursor, name)

            if asset:
                return AppAsset(
                    id=str(asset[0]),
                    name=asset[1],
                    image=asset[2],
                    mesh=asset[3],
                    description=asset[4],
                )
            else:
                raise ValueError(f"Asset {name} not found")
        except Exception as e:
            logger.error(f"Failed to get asset from the database: {e}")
            raise


@beartype
class AssetFinder:
    def __init__(self, assets: list[AppAsset]):
        self.threshold = 0.95
        self.asset_map = {asset.id: asset for asset in assets}

        embedding_function = SentenceTransformerEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )

        self.vector_store = Chroma(
            collection_name="app_assets",
            embedding_function=embedding_function,
            persist_directory="./asset_db",
        )

        self._populate_db(assets)

        self.llm = initialize_model("devstral:24b")
        self.rerank_chain = self._create_rerank_chain()

    def _populate_db(self, assets: list[AppAsset]):
        existing_ids = self.vector_store.get(include=[])["ids"]
        new_assets = [asset for asset in assets if asset.id not in existing_ids]

        if not new_assets:
            logger.info("ChromaDB collection is already up-to-date.")
            return

        logger.info(f"Adding {len(new_assets)} new assets to ChromaDB.")

        new_documents = [
            Document(
                page_content=asset.description,
                metadata={"id": asset.id, "name": asset.name},
            )
            for asset in new_assets
        ]

        self.vector_store.add_documents(
            new_documents, ids=[asset.id for asset in new_assets]
        )

    def delete_asset(self, asset_id: str):
        logger.info(f"Attempting to delete asset with ID: {asset_id}")
        try:
            if asset_id in self.asset_map:
                del self.asset_map[asset_id]
                logger.info(f"Removed asset '{asset_id}' from internal map.")
            else:
                logger.warning(f"Asset ID '{asset_id}' not found in internal map.")

            self.vector_store.delete(ids=[asset_id])
            logger.info(f"Successfully deleted asset '{asset_id}' from ChromaDB.")

        except Exception as e:
            logger.error(f"Failed to delete asset '{asset_id}': {e}")
            raise

    @beartype
    def clear_database(self):
        try:
            existing_ids = self.vector_store.get(include=[])["ids"]

            if not existing_ids:
                logger.info("Database is already empty. No action taken.")
                return

            self.vector_store.delete(ids=existing_ids)
            logger.info(
                f"Successfully deleted {len(existing_ids)} assets from ChromaDB."
            )

            self.asset_map.clear()
            logger.info("Cleared internal asset map.")

        except Exception as e:
            logger.error(f"An error occurred while clearing all assets: {e}")
            raise

    def _create_rerank_chain(self):
        system_prompt = f"""
    You are an expert asset-matching engine. Your primary goal is to find the single best asset from a provided list that matches a target description. All assets provided are a close match to the target, but your task is to identify the one that aligns most closely with the target description.

    Follow this exact process:
    1.  **Analyze Target:** Identify the core object and key attributes (e.g., color, material, style) from the 'Target Description'.
    2.  **Compare Assets:** For each asset in the 'Available Assets' list, evaluate how well its description matches the target's core object and attributes.
    3.  **Select the Winner:** Identify the single asset that is the strongest match.
    4.  **Final Decision Logic:**
        - If one or more assets are a strong match for the target, you MUST select one.
        - **If multiple assets are equally strong matches, you MUST choose the first one that appears in the list.** This is the tie-breaker rule.
        - There should ALWAYS be a match.

    Your output MUST be a JSON object with a single "data" key. The value will be the full JSON of the winning asset, or `null` if no match was found.
    """
        user_prompt = """
            Target Description:
            {description}

            Available Assets:
            {assets}

            Instructions:
            - Compare the target description with the descriptions of all assets.
            - Return the single best matching asset.
            - Be precise and conservative. Do not guess.

            You must respond ONLY with the JSON object of the best matching asset. Do not include any other text, explanations, or code.
            """
        parser = JsonOutputParser(pydantic_object=NullableAppAsset)
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", user_prompt)]
        )
        return prompt | self.llm | parser

    @beartype
    def find_by_description(self, description: str) -> NullableAppAsset:
        try:
            logger.info(f"Starting asset search for: '{description}'")

            candidate_docs = self.vector_store.similarity_search_with_relevance_scores(
                description, k=5
            )

            if not candidate_docs:
                logger.info("Semantic search returned no results.")
                return NullableAppAsset(asset=None)

            logger.info(f"Semantic search candidates: {candidate_docs}.")

            strong_candidates_docs = [
                doc for doc, score in candidate_docs if score >= self.threshold
            ]

            if not strong_candidates_docs:
                logger.info(f"No candidates met the threshold of {self.threshold}.")
                return NullableAppAsset(asset=None)

            candidates = [
                self.asset_map[doc.metadata["id"]]
                for doc in strong_candidates_docs
                if doc.metadata["id"] in self.asset_map
            ]
            candidates_json = json.dumps([asset.model_dump() for asset in candidates])

            result: NullableAppAsset = self.rerank_chain.invoke(
                {"description": description, "assets": candidates_json}
            )

            asset = NullableAppAsset(**result)

            if asset and asset.data:
                logger.info(f"LLM re-ranking selected asset ID: {asset.data.id}")
                return asset
            else:
                logger.info(
                    "LLM re-ranking concluded no asset was a sufficiently close match."
                )
                return asset

        except Exception as e:
            logger.error(f"Error while searching for an asset: {e}")
            return NullableAppAsset(asset=None)
