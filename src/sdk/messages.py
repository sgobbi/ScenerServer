from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from sdk.protobuf import message_pb2

import json


class IncomingMessageType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    GESTURE = "gesture"
    ERROR = "error"


class OutgoingMessageType(str, Enum):
    SESSION_START = "session_start"
    UNRELATED_RESPONSE = "unrelated_response"
    GENERATE_IMAGE = "generate_image"
    GENERATE_3D_OBJECT = "generate_3d_object"
    GENERATE_3D_SCENE = "generate_3d_scene"
    MODIFY_3D_SCENE = "modify_3d_scene"
    CONVERT_SPEECH = "convert_speech"
    ERROR = "error"


class IIncomingMessage(ABC):
    """Base class for all messages received from the client."""

    def from_proto(proto: message_pb2.Content) -> IIncomingMessage:
        try:
            msg_type = IncomingMessageType(proto.type)
        except ValueError:
            return IncomingUnknownMessage(original_type=proto.type)

        match msg_type:
            case IncomingMessageType.TEXT:
                return IncomingTextMessage(text=proto.text)
            case IncomingMessageType.AUDIO:
                return IncomingAudioMessage(data=proto.assets[0].data)
            case IncomingMessageType.GESTURE:
                return IncomingGestureMessage(data=proto.text)
            case IncomingMessageType.ERROR:
                return IncomingErrorMessage(status=proto.status, text=proto.text)


class IOutgoingMessage(ABC):
    """Base class for all messages sent to the client."""

    @abstractmethod
    def to_proto(self) -> message_pb2.Content:
        pass


@dataclass(frozen=True)
class IncomingTextMessage(IIncomingMessage):
    text: str


@dataclass(frozen=True)
class IncomingAudioMessage(IIncomingMessage):
    data: bytes


@dataclass(frozen=True)
class IncomingGestureMessage(IIncomingMessage):
    data: bytes


@dataclass(frozen=True)
class IncomingErrorMessage(IIncomingMessage):
    status: int
    text: str


@dataclass(frozen=True)
class IncomingUnknownMessage(IIncomingMessage):
    original_type: str


@dataclass(frozen=True)
class AppMediaAsset:
    id: str
    filename: str
    data: bytes


@dataclass(frozen=True)
class OutgoingSessionStartMessage(IOutgoingMessage):
    text: str

    def to_proto(self) -> message_pb2.Content:
        return message_pb2.Content(
            type=OutgoingMessageType.SESSION_START.value,
            text=self.text,
            status=200,
        )


@dataclass(frozen=True)
class OutgoingUnrelatedMessage(IOutgoingMessage):
    text: str

    def to_proto(self) -> message_pb2.Content:
        return message_pb2.Content(
            type=OutgoingMessageType.UNRELATED_RESPONSE.value,
            text=self.text,
            status=200,
        )


@dataclass(frozen=True)
class OutgoingConvertedSpeechMessage(IOutgoingMessage):
    text: str

    def to_proto(self) -> message_pb2.Content:
        return message_pb2.Content(
            type=OutgoingMessageType.CONVERT_SPEECH.value,
            text=self.text,
            status=200,
        )


@dataclass(frozen=True)
class OutgoingErrorMessage(IOutgoingMessage):
    status: int
    text: str

    def to_proto(self) -> message_pb2.Content:
        return message_pb2.Content(
            type=OutgoingMessageType.ERROR.value,
            status=self.status,
            error=self.text,
        )


@dataclass(frozen=True)
class OutgoingGeneratedImagesMessage(IOutgoingMessage):
    text: str
    assets: list[AppMediaAsset]

    def to_proto(self) -> message_pb2.Content:
        proto_assets = []

        for app_asset in self.assets:
            proto_assets.append(
                message_pb2.MediaAsset(
                    id=app_asset.id,
                    filename=app_asset.filename,
                    data=app_asset.data,
                )
            )

        return message_pb2.Content(
            type=OutgoingMessageType.GENERATE_IMAGE.value,
            text=self.text,
            assets=proto_assets,
            status=200,
        )


@dataclass(frozen=True)
class OutgoingGenerated3DObjectsMessage(IOutgoingMessage):
    text: str
    assets: list[AppMediaAsset]

    def to_proto(self) -> message_pb2.Content:
        proto_assets = []

        for app_asset in self.assets:
            proto_assets.append(
                message_pb2.MediaAsset(
                    id=app_asset.id,
                    filename=app_asset.filename,
                    data=app_asset.data,
                )
            )

        return message_pb2.Content(
            type=OutgoingMessageType.GENERATE_3D_OBJECT.value,
            text=self.text,
            assets=proto_assets,
            status=200,
        )


@dataclass(frozen=True)
class OutgoingGenerated3DSceneMessage(IOutgoingMessage):
    text: str
    json_scene: dict
    assets: list[AppMediaAsset]

    def to_proto(self) -> message_pb2.Content:
        proto_assets = []

        for app_asset in self.assets:
            proto_assets.append(
                message_pb2.MediaAsset(
                    id=app_asset.id,
                    filename=app_asset.filename,
                    data=app_asset.data,
                )
            )

        return message_pb2.Content(
            type=OutgoingMessageType.GENERATE_3D_SCENE.value,
            text=self.text,
            assets=proto_assets,
            status=200,
            metadata=json.dumps(self.json_scene),
        )


@dataclass(frozen=True)
class OutgoingModified3DSceneMessage(IOutgoingMessage):
    text: str
    modified_scene: dict
    assets: list[AppMediaAsset]

    def to_proto(self) -> message_pb2.Content:
        proto_assets = []

        for app_asset in self.assets:
            proto_assets.append(
                message_pb2.MediaAsset(
                    id=app_asset.id,
                    filename=app_asset.filename,
                    data=app_asset.data,
                )
            )

        return message_pb2.Content(
            type=OutgoingMessageType.MODIFY_3D_SCENE.value,
            text=self.text,
            assets=proto_assets,
            status=200,
            metadata=json.dumps(self.modified_scene),
        )
