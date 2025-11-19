from beartype import beartype
from langchain_core.tools import tool

from library.api import LibraryAPI
from pydantic import BaseModel


class DeleteAssetInput(BaseModel):
    name: str


class ClearDatabaseInput(BaseModel):
    pass


@tool
@beartype
def update_asset(
    api: LibraryAPI, name: str, image_path: str, mesh_path: str, description_path: str
) -> str:
    """Update an existing asset by name with image path, mesh path, and description path."""
    api.update_asset(name, image_path, mesh_path, description_path)
    return "asset updated"


@tool(args_schema=DeleteAssetInput)
@beartype
def delete_asset(api: LibraryAPI, name: str) -> str:
    """Delete an existing asset by name."""
    try:
        api.delete_asset(name)
        return f"Asset '{name}' deleted successfully."
    except Exception as e:
        return f"Failed to delete asset '{name}': {e}"


@tool(args_schema=ClearDatabaseInput)
@beartype
def clear_database(api: LibraryAPI) -> str:
    """Clean the database by removing all assets."""
    try:
        api.clear_database()
        return "Database cleared successfully."
    except Exception as e:
        raise
