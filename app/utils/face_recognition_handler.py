"""
Face Recognition Module for AttendAI
Uses DeepFace for high-accuracy face detection and recognition.

Install: pip install deepface tf-keras opencv-python-headless

How it works:
1. Student/Teacher registers face → image saved to static/faces/{user_id}/
2. Teacher runs recognition → webcam/uploaded photo compared against all enrolled faces
3. Matched students marked present automatically
"""

import os
import base64
import json
import numpy as np
from datetime import datetime
from pathlib import Path

# Face storage directory
FACES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'faces')


def get_face_dir(user_id):
    """Get the directory where a user's face images are stored."""
    d = os.path.join(FACES_DIR, str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def is_face_registered(user_id):
    """Check if a user has registered their face."""
    d = os.path.join(FACES_DIR, str(user_id))
    if not os.path.exists(d):
        return False
    images = [f for f in os.listdir(d) if f.endswith(('.jpg', '.png', '.jpeg'))]
    return len(images) > 0


def save_face_image(user_id, image_data_b64, filename=None):
    """
    Save a base64-encoded face image for a user.
    Validates that a face is actually present before saving.
    Returns (success, message)
    """
    try:
        # Decode base64 image
        if ',' in image_data_b64:
            image_data_b64 = image_data_b64.split(',')[1]
        image_bytes = base64.b64decode(image_data_b64)

        # Save temporarily for validation
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            # Validate face is present using DeepFace
            from deepface import DeepFace
            faces = DeepFace.extract_faces(
                img_path=tmp_path,
                detector_backend='opencv',
                enforce_detection=True
            )
            if not faces:
                return False, "No face detected in image. Please try again with better lighting."
        except ValueError as e:
            if 'Face could not be detected' in str(e):
                return False, "No face detected. Make sure your face is clearly visible."
            # DeepFace raises ValueError for no face — treat as no face found
            return False, f"Face detection failed: {str(e)}"
        finally:
            os.unlink(tmp_path)

        # Save validated image
        face_dir = get_face_dir(user_id)
        if not filename:
            filename = f"face_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        save_path = os.path.join(face_dir, filename)

        with open(save_path, 'wb') as f:
            f.write(image_bytes)

        return True, save_path

    except ImportError:
        return False, "DeepFace not installed. Run: pip install deepface tf-keras"
    except Exception as e:
        return False, f"Error saving face: {str(e)}"


def recognize_faces_in_image(image_data_b64, enrolled_student_ids, model_name='VGG-Face'):
    """
    Recognize faces in a classroom image and match against enrolled students.

    Args:
        image_data_b64: Base64-encoded classroom image
        enrolled_student_ids: List of student user IDs to check against
        model_name: DeepFace model ('VGG-Face', 'Facenet', 'ArcFace')

    Returns:
        dict with keys:
            'recognized': list of matched user_ids
            'unrecognized': count of faces found but not matched
            'total_faces': total faces detected
            'details': list of match detail dicts
            'error': error message if failed
    """
    try:
        from deepface import DeepFace
        import cv2
        import tempfile

        # Decode classroom image
        if ',' in image_data_b64:
            image_data_b64 = image_data_b64.split(',')[1]
        image_bytes = base64.b64decode(image_data_b64)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(image_bytes)
            classroom_img_path = tmp.name

        recognized_ids = []
        details = []
        total_faces = 0

        try:
            # Detect all faces in classroom image
            face_objs = DeepFace.extract_faces(
                img_path=classroom_img_path,
                detector_backend='opencv',
                enforce_detection=False
            )
            total_faces = len([f for f in face_objs if f.get('confidence', 0) > 0.5])

            # For each enrolled student with a registered face, try to find them
            for student_id in enrolled_student_ids:
                if not is_face_registered(student_id):
                    continue

                face_dir = os.path.join(FACES_DIR, str(student_id))

                try:
                    # Try to find this student's face in the classroom image
                    results = DeepFace.find(
                        img_path=classroom_img_path,
                        db_path=face_dir,
                        model_name=model_name,
                        detector_backend='opencv',
                        enforce_detection=False,
                        silent=True
                    )

                    # results is a list of DataFrames
                    matched = False
                    distance = None
                    if results and len(results) > 0:
                        df = results[0]
                        if not df.empty:
                            # Check if distance is below threshold (face recognized)
                            dist_col = [c for c in df.columns if 'distance' in c.lower()]
                            if dist_col:
                                min_dist = float(df[dist_col[0]].min())
                                # Threshold varies by model
                                thresholds = {
                                    'VGG-Face': 0.4,
                                    'Facenet': 0.4,
                                    'ArcFace': 0.68,
                                    'Facenet512': 0.3,
                                }
                                threshold = thresholds.get(model_name, 0.4)
                                if min_dist < threshold:
                                    matched = True
                                    distance = round(min_dist, 3)

                    if matched:
                        recognized_ids.append(student_id)
                        details.append({
                            'student_id': student_id,
                            'matched': True,
                            'confidence': round((1 - distance) * 100, 1),
                            'distance': distance
                        })

                except Exception as e:
                    # This student not found in image — that's OK
                    details.append({
                        'student_id': student_id,
                        'matched': False,
                        'error': str(e)
                    })

        finally:
            os.unlink(classroom_img_path)

        unrecognized = max(0, total_faces - len(recognized_ids))

        return {
            'recognized': recognized_ids,
            'unrecognized': unrecognized,
            'total_faces': total_faces,
            'details': details,
            'error': None
        }

    except ImportError:
        return {
            'recognized': [], 'unrecognized': 0, 'total_faces': 0,
            'details': [],
            'error': 'DeepFace not installed. Run: pip install deepface tf-keras opencv-python-headless'
        }
    except Exception as e:
        return {
            'recognized': [], 'unrecognized': 0, 'total_faces': 0,
            'details': [],
            'error': str(e)
        }


def delete_face_data(user_id):
    """Delete all face data for a user."""
    import shutil
    face_dir = os.path.join(FACES_DIR, str(user_id))
    if os.path.exists(face_dir):
        shutil.rmtree(face_dir)
        return True
    return False


def get_registered_count(student_ids):
    """Return count of students who have registered faces."""
    return sum(1 for sid in student_ids if is_face_registered(sid))
