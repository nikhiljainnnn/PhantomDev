"""
api/routes/github.py
────────────────────
API endpoints for GitHub interactions from the frontend.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import logging

from tools.github_tools import fetch_issue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

class IssueDetails(BaseModel):
    title: str
    body: str
    html_url: str

@router.get("/issue", response_model=IssueDetails)
def get_issue(repo: str = Query(...), issue_number: int = Query(...)):
    """
    Fetch an issue's title and body from GitHub given repo (e.g. org/name) and issue number.
    """
    try:
        issue = fetch_issue(repo, issue_number)
        return IssueDetails(
            title=issue["title"],
            body=issue["body"],
            html_url=issue["html_url"]
        )
    except ValueError as e:
        logger.warning(f"Validation error fetching issue: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in GET /github/issue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching GitHub issue.")
