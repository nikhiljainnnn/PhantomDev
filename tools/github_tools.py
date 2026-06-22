"""
tools/github_tools.py
──────────────────────
Wrapper around PyGithub for fetching issues and comments.
"""
import os
import logging
from typing import Dict, Any, Optional

try:
    from github import Github, GithubException
except ImportError:
    Github = None

logger = logging.getLogger(__name__)

def get_github_client() -> Optional['Github']:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token or not Github:
        return None
    return Github(token)

def fetch_issue(repo_name: str, issue_number: int) -> Dict[str, Any]:
    """
    Fetches an issue from GitHub and returns its title and body.
    Raises ValueError if GitHub is not configured or issue not found.
    """
    g = get_github_client()
    if not g:
        raise ValueError("GitHub integration is not configured. Missing GITHUB_TOKEN or PyGithub.")

    try:
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        
        return {
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "html_url": issue.html_url
        }
    except GithubException as e:
        logger.error(f"Failed to fetch issue {repo_name}#{issue_number}: {e}")
        if e.status == 404:
            raise ValueError(f"Issue #{issue_number} not found in {repo_name}.")
        raise ValueError(f"GitHub API error: {e.data.get('message', str(e))}")
    except Exception as e:
        logger.error(f"Unexpected error fetching issue: {e}")
        raise ValueError(f"Error fetching issue: {e}")
