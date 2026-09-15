import sys

from redis import Redis
from rq import Queue
from rq.worker import SimpleWorker

from app.core.config import get_settings


def main() -> None:
    connection = Redis.from_url(get_settings().redis_url)
    names = sys.argv[1:] or [
        "paper_parse",
        "knowledge_extract",
        "project_update",
        "scheme_generate",
        "default",
    ]
    queues = [
        Queue(name, connection=connection)
        for name in names
    ]
    # RQ's fork/spawn workers call os.wait4 in 2.10, which is unavailable on Windows.
    SimpleWorker(queues, connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
