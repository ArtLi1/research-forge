import os
import sys
from pathlib import Path

from chromadb.cli.cli import app

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    data_dir = Path(settings.chroma_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    sys.argv = [
        "chroma",
        "run",
        "--path",
        str(data_dir),
        "--host",
        settings.chroma_host,
        "--port",
        str(settings.chroma_port),
    ]
    app()


if __name__ == "__main__":
    main()
