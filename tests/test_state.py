import pytest
from datetime import datetime, timedelta
from orchestrator.state import TaskState

def test_task_state_update_status_terminal():
    """
    Test that updating the status to a terminal status sets the end_time attribute.
    """
    task_state = TaskState()
    task_state.update_status("PR_OPEN")
    assert task_state.end_time is not None
    current_time = datetime.now()
    end_time = datetime.fromisoformat(task_state.end_time)
    assert (current_time - end_time) < timedelta(seconds=1)

def test_task_state_update_status_non_terminal():
    """
    Test that updating the status to a non-terminal status does not set the end_time attribute.
    """
    task_state = TaskState()
    task_state.update_status("IN_PROGRESS")
    assert task_state.end_time is None

def test_task_state_update_status_terminal_multiple():
    """
    Test that updating the status to multiple terminal statuses sets the end_time attribute correctly.
    """
    task_state = TaskState()
    task_state.update_status("PR_OPEN")
    initial_end_time = task_state.end_time
    task_state.update_status("FAILED")
    assert task_state.end_time != initial_end_time
    current_time = datetime.now()
    end_time = datetime.fromisoformat(task_state.end_time)
    assert (current_time - end_time) < timedelta(seconds=1)

def test_task_state_end_time_iso_format():
    """
    Test that the end_time attribute is in ISO-8601 format.
    """
    task_state = TaskState()
    task_state.update_status("PR_OPEN")
    end_time = datetime.fromisoformat(task_state.end_time)
    assert end_time is not None