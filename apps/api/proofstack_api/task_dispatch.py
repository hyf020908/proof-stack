"""Task backend adapter that keeps inline and Redis modes behind one contract."""

from fastapi import BackgroundTasks, HTTPException
from proofstack_shared.config import Settings


def dispatch_analysis(
    analysis_id: str,
    *,
    background_tasks: BackgroundTasks,
    settings: Settings,
) -> str:
    if settings.task_backend == "inline":
        from proofstack_worker.tasks import run_analysis

        background_tasks.add_task(run_analysis, analysis_id)
        return f"inline:{analysis_id}"
    try:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        queue = Queue("proofstack", connection=connection, default_timeout=3600)
        job = queue.enqueue("proofstack_worker.tasks.run_analysis", analysis_id, job_timeout=3600)
        return str(job.id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The Redis task backend is unavailable; use inline mode or start Redis "
                "and the worker"
            ),
        ) from exc
