import cv2


def crop_hand(frame, landmarks):
    h, w, _ = frame.shape
    xs = [int(lm.x * w) for lm in landmarks]
    ys = [int(lm.y * h) for lm in landmarks]
    x_min, x_max = max(min(xs) - 50, 0), min(max(xs) + 50, w)
    y_min, y_max = max(min(ys) - 50, 0), min(max(ys) + 50, h)
    return frame[y_min:y_max, x_min:x_max]
