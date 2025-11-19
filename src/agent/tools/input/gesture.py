# from langchain_core.tools import tool
# from langchain_ollama import ChatOllama
# from colorama import Fore
# from loguru import logger
# from mediapipe.tasks import python
# from mediapipe.tasks.python import vision
# import mediapipe as mp
# import numpy as np
# import cv2


# @tool
# def hand_gesture(path: str) -> str:
#     """Convert an image to a hand gesture info"""

#     # Load the model
#     base_options = python.BaseOptions(
#         model_asset_path="../model/mediapipe/gesture_recognizer.task"
#     )
#     options = vision.GestureRecognizerOptions(base_options=base_options)
#     recognizer = vision.GestureRecognizer.create_from_options(options)

#     # Convert image to RGB and wrap as MediaPipe image
#     rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#     mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

#     # Run gesture recognizer
#     result = recognizer.recognize(mp_image)

#     # Get top gesture
#     if result.gestures:
#         top_gesture = result.gestures[0][0]
#         gesture_text = f"{top_gesture.category_name} ({top_gesture.score:.2f})"
#         return gesture_text
