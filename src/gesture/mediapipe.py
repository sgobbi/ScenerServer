from gesture.hand import Hand
from gesture.image import crop_hand
from mediapipe.tasks.python import vision
from mediapipe.framework.formats import landmark_pb2
import mediapipe as mp
import numpy as np
import threading
import time
import cv2


class Mediapipe:
    # Main function
    def __init__(self):
        """Initialize parameters"""

        # Mediapipe - utils
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_hands = mp.solutions.hands
        self.mp_drawing_styles = mp.solutions.drawing_styles

        # Mediapipe - Gesture Recognizer setup
        base_options = mp.tasks.BaseOptions(
            model_asset_path="model/mediapipe/gesture_recognizer.task",
            delegate=mp.tasks.BaseOptions.Delegate.GPU,
        )
        options = vision.GestureRecognizerOptions(base_options=base_options)
        self.recognizer = vision.GestureRecognizer.create_from_options(options)

        # Mediapipe - Hand detector
        base_options = mp.tasks.BaseOptions(
            model_asset_path="model/mediapipe/hand_landmarker.task",
            delegate=mp.tasks.BaseOptions.Delegate.GPU,
        )
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,
            num_hands=2,
            result_callback=self.callback_detection,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        # Instantiate hand objects
        self.hand_right = Hand("Right")
        self.hand_left = Hand("Left")

        # Async stuff
        self.frame = None
        self.detection = None
        self.duration = None
        self.lock = threading.Lock()

    # Processing draw_hand_stuff
    def callback_detection(self, detection, output_image, timestamp_ms):
        with self.lock:
            np_image = output_image.numpy_view()
            self.frame = cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)
            self.detection = detection

    def process_detection(self, frame, cap):
        """Detect hand landmarks"""
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.array(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
        )
        timestamp = int(time.time() * 1000)
        detection = self.detector.detect_async(mp_image, timestamp)
        return detection

    def process_hand(self, detection, frame, hand):
        """Store results in Hand object"""
        # Find hand index
        list_landmarks = detection.hand_landmarks
        list_handedness = detection.handedness
        for i in range(len(list_landmarks)):
            if list_handedness[i][0].category_name == hand.label:
                hand.index = i
                break
        if hand.index is None:
            return

        # Fill hand stuff
        if len(list_landmarks) >= hand.index + 1:
            hand.add_landmark(list_landmarks[hand.index])
            hand.image = crop_hand(frame, hand.landmarks)
            self.process_gesture(hand)

    def process_gesture(self, hand):
        """Recognize hand gesture"""
        rgb_frame = cv2.cvtColor(hand.image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        detection = self.recognizer.recognize(mp_image)
        if detection.gestures:
            gesture = detection.gestures[0][0]
            hand.add_gesture(gesture.category_name)
            hand.score = gesture.score

    # Drawing stuff
    def draw_result(self, frame):
        bw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        bw = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
        self.draw_hand_stuff(bw, self.hand_left)
        self.draw_hand_stuff(bw, self.hand_right)
        self.draw_fps(bw)
        cv2.imshow("Hand gesture", bw)

    def draw_subimages(self):
        if self.hand_left.image is not None:
            cv2.imshow(self.hand_left.label, self.hand_left.image)
        if self.hand_right.image is not None:
            cv2.imshow(self.hand_right.label, self.hand_right.image)

    def draw_hand_stuff(self, frame, hand):
        # Draw hand landmarks
        if hand.landmarks is not None:
            hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
            hand_landmarks_proto.landmark.extend(
                [
                    landmark_pb2.NormalizedLandmark(
                        x=landmark.x, y=landmark.y, z=landmark.z
                    )
                    for landmark in hand.landmarks
                ]
            )
            self.mp_drawing.draw_landmarks(
                frame,
                hand_landmarks_proto,
                self.mp_hands.HAND_CONNECTIONS,
                self.mp_drawing_styles.get_default_hand_landmarks_style(),
                self.mp_drawing_styles.get_default_hand_connections_style(),
            )

            # Get the top left corner of the detected hand's bounding box.
            height, width, _ = frame.shape
            x_coordinates = [landmark.x for landmark in hand.landmarks]
            y_coordinates = [landmark.y for landmark in hand.landmarks]
            x = int(min(x_coordinates) * width)
            y = int(min(y_coordinates) * height) - 10

            # Draw hand label
            score_text = f"{hand.score:.2f}" if hand.score is not None else "N/A"
            grabbing_text = f"Grabbing" if hand.grabbing is True else ""
            cv2.putText(
                frame,
                hand.label,
                (x - 100, y - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
            cv2.putText(
                frame,
                hand.gesture,
                (x - 100, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
            cv2.putText(
                frame,
                score_text,
                (x - 100, y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
            cv2.putText(
                frame,
                grabbing_text,
                (x - 100, y + 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )

    def draw_fps(self, frame):
        fps = 1.0 / self.duration
        text = f"FPS: {fps:.2f} | {(self.duration)*1000:.2f} ms"
        cv2.putText(
            frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
        )

    def test(self):
        """Test with webcam"""
        # Webcam feed
        cap = cv2.VideoCapture(0)

        while cap.isOpened():
            # New frame
            start = time.time()
            self.hand_left.reset()
            self.hand_right.reset()
            ret, frame = cap.read()
            if not ret:
                break

            # Hand detection
            detection = self.process_detection(frame, cap)

            # Show frame
            with self.lock:
                if self.frame is not None:
                    self.process_hand(self.detection, self.frame, self.hand_left)
                    self.process_hand(self.detection, self.frame, self.hand_right)
                    self.draw_result(self.frame)

            # Loop exit
            self.duration = time.time() - start
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()
