import os

from beartype import beartype
from pathlib import Path

import torch

os.environ["ATTN_BACKEND"] = (
    "xformers"  # Can be 'flash-attn' or 'xformers', default is 'flash-attn'
)
os.environ["SPCONV_ALGO"] = "native"  # Can be 'native' or 'auto', default is 'auto'.
# 'auto' is faster but will do benchmarking at the beginning.
# Recommended to set to 'native' if run only once.

from PIL import Image

from TRELLIS.trellis.pipelines import TrellisImageTo3DPipeline
from TRELLIS.trellis.utils import postprocessing_utils


@beartype
def read_glb(object_path: str):
    with open(object_path, "rb") as f:
        return f.read()


@beartype
def generate(image_path: Path, image_id: str):
    # Load a pipeline from a model folder or a Hugging Face model hub.
    pipeline = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
    pipeline.cuda()

    # Load an image
    image = Image.open(image_path)

    # Run the pipeline
    outputs = pipeline.run(
        image,
        seed=1,
        # Optional parameters
        sparse_structure_sampler_params={
            "steps": 12,
            "cfg_strength": 7.5,
        },
        slat_sampler_params={
            "steps": 12,
            "cfg_strength": 3,
        },
    )

    # GLB files can be extracted from the outputs
    glb = postprocessing_utils.to_glb(
        outputs["gaussian"][0],
        outputs["mesh"][0],
        # Optional parameters
        simplify=0.95,  # Ratio of triangles to remove in the simplification process
        texture_size=256,  # Size of the texture used for the GLB
    )
    glb.export(image_path.parent / f"{image_id}.glb")

    del pipeline
    torch.cuda.empty_cache()


if __name__ == "__main__":
    generate(Path("steampunk_boat.png"), "1")
