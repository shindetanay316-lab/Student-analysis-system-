from datetime import timezone
from models import db
from workflow_models import WorkflowReview, now


def claim(review):
    expiry = review.expires_at.replace(tzinfo=timezone.utc) if review.expires_at.tzinfo is None else review.expires_at
    if expiry <= now():
        raise ValueError('This preview expired. Create a fresh preview.')
    count = db.session.execute(db.update(WorkflowReview).where(WorkflowReview.token==review.token,
        WorkflowReview.confirmed_at.is_(None),WorkflowReview.claimed.is_(False)).values(claimed=True)).rowcount
    if count != 1:
        raise ValueError('This preview was already processed. Reload before continuing.')
