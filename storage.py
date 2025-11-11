# Dataset Storage that creates, organizes, and saves each task with screenshots + metadata

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class DatasetStorage:

    def __init__(self, task_name: str, app_name: str):
        # Sanitize names and remove special characters
        self.task_name = self._sanitize(task_name)
        self.app_name = self._sanitize(app_name)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create directory structure
        base_path = Path(os.getenv('SCREENSHOT_DIR', 'dataset'))
        self.task_dir = base_path / self.app_name / f"{self.task_name}_{self.timestamp}"
        self.screenshots_dir = self.task_dir / "screenshots"

        # Create directories
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Initialize metadata
        self.metadata = {
            "task_name": task_name,
            "app_name": app_name,
            "timestamp": self.timestamp,
            "created_at": datetime.now().isoformat(),
            "screenshots": []
        }

        self.screenshot_count = 0

    def save_screenshot(
        self,
        screenshot_bytes: bytes,
        name: str,
        description: str,
        url: str,
        action: Optional[Dict[str, Any]] = None
    ) -> str:

        # Save screenshot file
        filename = f"{name}.png"
        filepath = self.screenshots_dir / filename

        with open(filepath, 'wb') as f:
            f.write(screenshot_bytes)

        # Record metadata
        screenshot_meta = {
            "filename": filename,
            "name": name,
            "description": description,
            "url": url,
            "captured_at": datetime.now().isoformat(),
            "path": f"screenshots/{filename}"
        }

        # Add action info if provided
        if action:
            screenshot_meta["action"] = action.get("action")
            screenshot_meta["selector"] = action.get("selector")

        self.metadata["screenshots"].append(screenshot_meta)
        self.screenshot_count += 1

        return str(filepath)

    def save_metadata(
        self,
        instruction: str,
        task_info: Dict[str, Any],
        action_history: list,
        error: str = None
    ) -> str:

        # Add final metadata
        self.metadata["instruction"] = instruction
        self.metadata["task_info"] = task_info
        self.metadata["total_screenshots"] = self.screenshot_count
        self.metadata["completed_at"] = datetime.now().isoformat()

        # Add error if task failed
        if error:
            self.metadata["error"] = error
            self.metadata["status"] = "failed"
        else:
            self.metadata["status"] = "completed"

        # Save metadata file
        metadata_path = self.task_dir / "metadata.json"

        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        return str(metadata_path)

    @staticmethod
    def _sanitize(name: str) -> str:

        sanitized = "".join(
            c if c.isalnum() or c in ('-', '_') else '_'
            for c in name
        )

        # Remove consecutive underscores
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')

        return sanitized.strip('_').lower()
