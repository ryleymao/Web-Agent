# State Detector that uses perceptual hashing to detect UI state changes

import io
from typing import Set
from PIL import Image
import imagehash


class StateDetector:
    def __init__(self, similarity_threshold: int = 5):
        # Lowering the threshold makes it more sensitive and has fewer duplicates
        self.similarity_threshold = similarity_threshold
        self.seen_states: Set[imagehash.ImageHash] = set()

    def is_new_state(self, screenshot_bytes: bytes, force_save: bool = False) -> bool:
        # Check to see if this screenshot shows a new UI state
        if force_save:
            return True

        # Compute perceptual hash
        image = Image.open(io.BytesIO(screenshot_bytes))
        current_hash = imagehash.phash(image, hash_size=16)

        # Compare to previous states
        for seen_hash in self.seen_states:
            difference = current_hash - seen_hash
            if difference <= self.similarity_threshold:
                return False  # Duplicate state

        # New state detected
        self.seen_states.add(current_hash)
        return True

    def reset(self):
        # Clear state history between tasks
        self.seen_states.clear()
