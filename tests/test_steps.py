import pytest
from pathlib import Path

def test_steps_file_exists():
    """Test if the steps file exists."""
    steps_file = Path("docs/steps.md")
    assert steps_file.exists()

def test_steps_file_content():
    """Test if the steps file has the correct content."""
    steps_file = Path("docs/steps.md")
    with open(steps_file, "r") as f:
        content = f.read()
    assert "Step-by-Step Guide" in content
    assert "Step 1: Issue Creation" in content
    assert "Step 2: Task Assignment" in content
    assert "Step 3: Requirements Extraction" in content
    assert "Step 4: Architecture Design" in content
    assert "Step 5: Implementation" in content
    assert "Step 6: Testing" in content
    assert "Step 7: Deployment" in content