import pytest
from pathlib import Path

def test_workflow_file_exists():
    """Test if the workflow file exists."""
    workflow_file = Path("docs/workflow.md")
    assert workflow_file.exists()

def test_workflow_file_content():
    """Test if the workflow file has the correct content."""
    workflow_file = Path("docs/workflow.md")
    with open(workflow_file, "r") as f:
        content = f.read()
    assert "Project Workflow" in content
    assert "Issue creation" in content
    assert "Task assignment" in content
    assert "Requirements extraction" in content
    assert "Architecture design" in content
    assert "Implementation" in content
    assert "Testing" in content
    assert "Deployment" in content