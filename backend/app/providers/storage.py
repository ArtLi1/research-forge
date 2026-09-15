import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError


class LocalPaperStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().paper_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, paper_id: uuid.UUID) -> tuple[Path, str]:
        import hashlib

        suffix = Path(upload.filename or "").suffix.lower()
        if suffix != ".pdf" or upload.content_type not in {
            "application/pdf",
            "application/x-pdf",
            "application/octet-stream",
        }:
            raise AppError("UNSUPPORTED_PDF", "仅支持 PDF 文件", status_code=415)

        destination = (self.root / f"{paper_id}.pdf").resolve()
        if destination.parent != self.root:
            raise AppError("UNSUPPORTED_PDF", "非法文件路径", status_code=400)

        limit = get_settings().max_upload_mb * 1024 * 1024
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("wb") as target:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise AppError(
                            "UNSUPPORTED_PDF",
                            f"PDF 不得超过 {get_settings().max_upload_mb} MB",
                            status_code=413,
                        )
                    digest.update(chunk)
                    target.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return destination, digest.hexdigest()

    def delete(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved.parent == self.root:
            resolved.unlink(missing_ok=True)
