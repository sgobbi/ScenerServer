from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, Union, Annotated


class ColorRGBA(BaseModel):
    r: float
    g: float
    b: float
    a: float | None


class Vector3(BaseModel):
    x: float
    y: float
    z: float

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]


class Vector4(BaseModel):
    x: float
    y: float
    z: float
    w: float

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.w]


class ComponentType(str, Enum):
    LIGHT = "light"
    PRIMITIVE = "primitive"
    DYNAMIC = "dynamic"


class SkyboxType(str, Enum):
    GRADIENT = "gradient"
    SUN = "sun"
    CUBED = "cubed"


class LightType(str, Enum):
    SPOT = "spot"
    DIRECTIONAL = "directional"
    POINT = "point"
    AREA = "area"


class LightShadowType(str, Enum):
    NO_SHADOWS = "no_shadows"
    HARD_SHADOWS = "hard_shadows"
    SOFT_SHADOWS = "soft_shadows"


class LightMode(str, Enum):
    BAKED = "baked"
    MIXED = "mixed"
    REALTIME = "realtime"


class AreaLightShape(str, Enum):
    RECTANGLE = "rectangle"
    DISK = "disk"


class PrimitiveShape(str, Enum):
    CUBE = "cube"
    SPHERE = "sphere"
    CAPSULE = "capsule"
    CYLINDER = "cylinder"
    PLANE = "plane"
    QUAD = "quad"


class SceneComponent(BaseModel):
    component_type: ComponentType


class PrimitiveObject(SceneComponent):
    component_type: Literal[ComponentType.PRIMITIVE] = ComponentType.PRIMITIVE
    shape: PrimitiveShape
    color: ColorRGBA | None


class DynamicObject(SceneComponent):
    component_type: Literal[ComponentType.DYNAMIC] = ComponentType.DYNAMIC
    id: str


class BaseLight(BaseModel):
    component_type: Literal[ComponentType.LIGHT] = ComponentType.LIGHT
    type: LightType
    color: ColorRGBA
    intensity: float
    indirect_multiplier: float


class SpotLight(BaseLight):
    type: Literal[LightType.SPOT] = LightType.SPOT
    range: float
    spot_angle: float
    mode: LightMode
    shadow_type: LightShadowType


class DirectionalLight(BaseLight):
    type: Literal[LightType.DIRECTIONAL] = LightType.DIRECTIONAL
    mode: LightMode
    shadow_type: LightShadowType


class PointLight(BaseLight):
    type: Literal[LightType.POINT] = LightType.POINT
    range: float
    mode: LightMode
    shadow_type: LightShadowType


class AreaLight(BaseLight):
    type: Literal[LightType.AREA] = LightType.AREA
    shape: AreaLightShape
    range: float
    width: float | None
    height: float | None
    radius: float | None

    @model_validator(mode="after")
    def check_conditional_fields(self):
        if (
            self.shape == AreaLightShape.RECTANGLE
            and self.width is None
            or self.height is None
        ):
            raise ValueError("width and height must be set for rectangle area light")
        if self.shape == AreaLightShape.DISK and self.radius is None:
            raise ValueError("radius must be set for disk area light")
        return self


class GradientSkybox(BaseModel):
    type: Literal[SkyboxType.GRADIENT] = SkyboxType.GRADIENT
    color1: ColorRGBA
    color2: ColorRGBA
    up_vector: Vector4
    intensity: float
    exponent: float


class SunSkybox(BaseModel):
    type: Literal[SkyboxType.SUN] = SkyboxType.SUN
    top_color: ColorRGBA
    top_exponent: float
    horizon_color: ColorRGBA
    bottom_color: ColorRGBA
    bottom_exponent: float
    sky_intensity: float
    sun_color: ColorRGBA
    sun_intensity: float
    sun_alpha: float
    sun_beta: float
    sun_vector: Vector4


class CubedSkybox(BaseModel):
    type: Literal[SkyboxType.CUBED] = SkyboxType.CUBED
    tint_color: ColorRGBA
    exposure: float
    rotation: float
    cube_map: str


Skybox = Annotated[
    Union[GradientSkybox, SunSkybox, CubedSkybox], Field(discriminator="type")
]

Light = Annotated[
    Union[SpotLight, DirectionalLight, PointLight, AreaLight],
    Field(discriminator="type"),
]

Component = Annotated[
    Union[PrimitiveObject, DynamicObject, Light],
    Field(discriminator="component_type"),
]


class SceneObject(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = Field(default=None)
    position: Vector3
    rotation: Vector3
    scale: Vector3
    components: list[Component]
    children: list["SceneObject"]


class Scene(BaseModel):
    name: str
    skybox: Optional[Skybox]
    graph: list[SceneObject]


class FinalDecompositionOutput(BaseModel):
    scene: Scene
