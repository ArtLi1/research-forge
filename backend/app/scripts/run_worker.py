import os
import sys

from redis import Redis
from rq import Queue
from rq.worker import SimpleWorker, Worker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.tasks.types import TASK_SPECS


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    names = sys.argv[1:] or [str(kind) for kind in TASK_SPECS]
    with Redis.from_url(settings.redis_url, socket_connect_timeout=5) as connection:
        queues = [Queue(name, connection=connection) for name in names]
        # The async runner enforces deadlines and DB heartbeats on both platforms.
        worker = SimpleWorker if os.name == "nt" else Worker
        worker(queues, connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
