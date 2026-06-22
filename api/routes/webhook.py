"""
api/routes/webhook.py
──────────────────────
GitHub webhook receiver to automatically trigger PhantomDev pipelines.
"""
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import hmac
import hashlib
import os
import logging
import json

from orchestrator.state import TaskState
from api.store import task_store
from worker.celery_app import run_pipeline


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not secret:
        # If no secret configured, reject or accept based on strictness. We will reject for security.
        logger.warning("WEBHOOK_SECRET is not configured.")
        return False

    hash_object = hmac.new(secret.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("x-hub-signature-256")
    event_type = request.headers.get("x-github-event")

    body = await request.body()

    if not signature or not verify_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if event_type == "issues":
        action = payload.get("action")
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        
        # Check if it has 'phantomdev' label when opened
        labels = [l.get("name") for l in issue.get("labels", [])]
        if action in ["opened", "labeled"] and "phantomdev" in labels:
            logger.info(f"Triggering pipeline from issue #{issue.get('number')}")
            await dispatch_pipeline(issue, repo, background_tasks)
            return {"status": "Pipeline triggered"}
            
    elif event_type == "issue_comment":
        action = payload.get("action")
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        
        if action == "created" and "@phantomdev run" in comment.get("body", "").lower():
            logger.info(f"Triggering pipeline from comment on issue #{issue.get('number')}")
            await dispatch_pipeline(issue, repo, background_tasks)
            return {"status": "Pipeline triggered"}

    return {"status": "Ignored"}

async def dispatch_pipeline(issue: dict, repo: dict, background_tasks: BackgroundTasks):
    state = TaskState(
        github_issue_number=issue.get("number"),
        github_issue_title=issue.get("title", ""),
        github_issue_body=issue.get("body", "") or "No description provided.",
        target_repo=repo.get("full_name", ""),
        base_branch=repo.get("default_branch", "main"),
    )
    await task_store.save(state)
    from api.main import _run_pipeline_bg, USE_CELERY, websocket_connections
    websocket_connections[state.task_id] = []

    if USE_CELERY:
        run_pipeline.delay(state.task_id, state.model_dump_json())
        logger.info("Task %s dispatched to Celery via Webhook", state.task_id)
    else:
        background_tasks.add_task(_run_pipeline_bg, state.task_id)
        logger.info("Task %s started in BackgroundTasks via Webhook", state.task_id)
