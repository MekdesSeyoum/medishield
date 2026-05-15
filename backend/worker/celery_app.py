import sys
from pathlib import Path

from celery import Celery

# Ensure the backend root is on sys.path so all internal packages are importable
# regardless of which directory the worker process was launched from.
_backend_root = str(Path(__file__).parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from core.config import get_settings


def _make_celery() -> Celery:
    s = get_settings()
    app = Celery(
        "medishield",
        broker=s.redis_url,
        backend=s.redis_url,
        include=["worker.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = _make_celery()
