from gesture.utils import compute_rotation, compute_position, compute_displacement
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from collections import deque
import mediapipe as mp
import numpy as np
import threading
import cv2


class Hand:
    # Main function
    def __init__(self, label):
        """Initialize parameters"""
        # Info stuff
        self.index = None
        self.image = None
        self.label = label

        # Detection stuff
        self.landmarks = None
        self.gesture = None
        self.score = None

        # Dynamic stuff
        self.pose = None
        self.rotation = None
        self.grabbing = False
        self.list_pose = deque(maxlen=50)
        self.list_rotation = deque(maxlen=50)
        self.lock = threading.Lock()

        if label not in ("Right", "Left"):
            raise ValueError("name must be 'Right' or 'Left'")

    def add_landmark(self, landmarks):
        self.landmarks = landmarks
        pose = compute_position(landmarks)
        rotation = compute_rotation(landmarks)

        with self.lock:
            self.list_pose.append(pose)
            self.list_rotation.append(rotation)

            displacment = compute_displacement(self.list_pose)
            print(displacment)

    def add_gesture(self, gesture):
        self.gesture = gesture

        if gesture == "Closed_Fist":
            self.grabbing = True
        elif gesture == "Open_Palm" and self.grabbing == True:
            self.grabbing = False

    def reset(self):
        self.index = None
        self.image = None
        self.pose = None
        self.rotation = None
        self.landmarks = None
        self.gesture = None
        self.score = None
