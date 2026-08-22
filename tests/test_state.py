from orchestrator.state import TaskState, TaskStatus


def test_task_state_set_status():
    """
    Test that setting the status updates the updated_at attribute.
    """
    import time
    task_state = TaskState()
    initial_updated_at = task_state.updated_at
    
    time.sleep(0.001)  # Ensure timestamp differs
    task_state.set_status(TaskStatus.PR_OPEN)
    assert task_state.status == TaskStatus.PR_OPEN
    assert task_state.updated_at != initial_updated_at

def test_task_state_fail():
    """
    Test fail method.
    """
    task_state = TaskState()
    task_state.fail("Some error")
    assert task_state.status == TaskStatus.FAILED
    assert "Some error" in task_state.errors