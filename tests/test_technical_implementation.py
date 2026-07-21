import pytest
from pathlib import Path

def test_technical_implementation_file_exists():
    """Test if the technical implementation file exists."""
    technical_implementation_file = Path("docs/technical_implementation.md")
    assert technical_implementation_file.exists()

def test_technical_implementation_file_content():
    """Test if the technical implementation file has the correct content."""
    technical_implementation_file = Path("docs/technical_implementation.md")
    with open(technical_implementation_file, "r") as f:
        content = f.read()
    assert "Technical Implementation Overview" in content
    assert "Architecture" in content
    assert "API Contracts" in content
    assert "Implementation Details" in content
    assert "Tools and Technologies" in content