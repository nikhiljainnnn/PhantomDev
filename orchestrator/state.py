from datetime import datetime
from typing import Optional

class TaskState:
    def __init__(self):
        """
        Initialize a new TaskState object.

        Sets the start_time attribute to the current timestamp.
        """
        self.start_time: str = datetime.now().isoformat()
        self.end_time: Optional[str] = None
        # ... existing attributes ...

    def update_status(self, status: str):
        """
        Update the status of the task.

        If the task reaches a terminal status, sets the end_time attribute to the current timestamp.

        Args:
            status (str): The new status of the task.
        """
        # ... existing logic ...
        terminal_statuses = ["PR_OPEN", "FAILED"]
        if status in terminal_statuses:
            self.end_time = datetime.now().isoformat()
        # ... existing logic ...