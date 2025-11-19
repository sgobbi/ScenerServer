from pydantic import BaseModel, Field
from typing import Literal, Optional, Union, Annotated

from sdk.scene import (
    AreaLightShape,
    ColorRGBA,
    ComponentType,
    LightMode,
    LightShadowType,
    LightType,
    PrimitiveShape,
    Vector3,
)


class BaseLightUpdate(BaseModel):
    component_type: Literal[ComponentType.LIGHT] = ComponentType.LIGHT
    type: LightType
    color: Optional[ColorRGBA] = None
    intensity: Optional[float] = None
    indirect_multiplier: Optional[float] = None


class SpotLightUpdate(BaseLightUpdate):
    type: Literal[LightType.SPOT] = LightType.SPOT
    range: Optional[float] = None
    spot_angle: Optional[float] = None
    mode: Optional[LightMode] = None
    shadow_type: Optional[LightShadowType] = None


class DirectionalLightUpdate(BaseLightUpdate):
    type: Literal[LightType.DIRECTIONAL] = LightType.DIRECTIONAL
    mode: Optional[LightMode] = None
    shadow_type: Optional[LightShadowType] = None


class PointLightUpdate(BaseLightUpdate):
    type: Literal[LightType.POINT] = LightType.POINT
    range: Optional[float] = None
    mode: Optional[LightMode] = None
    shadow_type: Optional[LightShadowType] = None


class AreaLightUpdate(BaseLightUpdate):
    type: Literal[LightType.AREA] = LightType.AREA
    shape: Optional[AreaLightShape] = None
    range: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    radius: Optional[float] = None


class PrimitiveObjectUpdate(BaseModel):
    component_type: Literal[ComponentType.PRIMITIVE] = ComponentType.PRIMITIVE
    shape: Optional[PrimitiveShape] = None
    color: Optional[ColorRGBA] = None


LightUpdate = Annotated[
    Union[SpotLightUpdate, DirectionalLightUpdate, PointLightUpdate, AreaLightUpdate],
    Field(discriminator="type"),
]

ComponentUpdate = Annotated[
    Union[
        LightUpdate,
        PrimitiveObjectUpdate,
    ],
    Field(discriminator="component_type"),
]


class SceneObjectUpdate(BaseModel):
    id: str
    parent_id: Optional[str] = None
    position: Optional[Vector3] = None
    rotation: Optional[Vector3] = None
    scale: Optional[Vector3] = None
    components_to_update: Optional[list[ComponentUpdate]] = None
