"""Redis Queue worker process entry point."""

from proofstack_shared.config import get_settings
from proofstack_shared.logging import configure_logging
from redis import Redis
from rq import Queue, Worker


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    connection = Redis.from_url(settings.redis_url)
    worker = Worker([Queue("proofstack", connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
