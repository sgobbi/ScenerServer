import numpy as np


def compute_rotation(landmarks):
    # rotation
    wrist = np.array([landmarks[0].x, landmarks[0].y, landmarks[0].z])
    index = np.array([landmarks[5].x, landmarks[5].y, landmarks[5].z])
    pinky = np.array([landmarks[17].x, landmarks[17].y, landmarks[17].z])

    x_axis = index - wrist
    x_axis /= np.linalg.norm(x_axis)

    y_axis = pinky - wrist
    y_axis /= np.linalg.norm(y_axis)

    z_axis = np.cross(x_axis, y_axis)
    z_axis /= np.linalg.norm(z_axis)

    y_axis = np.cross(z_axis, x_axis)  # ensure orthogonality

    rotation_matrix = np.stack([x_axis, y_axis, z_axis], axis=1)
    return rotation_matrix


def compute_position(landmarks):
    coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks])
    mean_position = coords.mean(axis=0)
    return mean_position


def compute_displacement(list_pose, smoothing=True, window=5, threshold=0.02):
    list_pose = np.array(list_pose)

    if list_pose.shape[0] < 2:
        return np.zeros(3)

    if smoothing and list_pose.shape[0] >= window:
        kernel = np.ones(window) / window
        smoothed = np.zeros_like(list_pose)
        for i in range(3):  # x, y, z
            smoothed[:, i] = np.convolve(list_pose[:, i], kernel, mode="same")
        list_pose = smoothed

    displacement = list_pose[-1] - list_pose[0]

    # ❄️ Appliquer le threshold
    displacement[np.abs(displacement) <= threshold] = 0

    return displacement


def compute_rotation_delta(list_rotation, threshold=1.0):
    list_rotation = np.array(list_rotation)

    if list_rotation.shape[0] < 2:
        return np.zeros(3)

    # delta = dernière rotation - première rotation
    delta = list_rotation[-1] - list_rotation[0]

    # Appliquer le threshold
    delta[np.abs(delta) <= threshold] = 0

    return delta
