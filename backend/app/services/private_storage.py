"""Keep backend credentials and cloud job/source files out of the public mount."""
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from .. import config


class PublicStorage(StaticFiles):
    async def get_response(self, path: str, scope):
        resolved = (Path(self.directory) / path).resolve()
        for private in (config.SECRETS_DIR, config.STORAGE_DIR / "cloud"):
            if resolved.is_relative_to(private.resolve()):
                raise HTTPException(404)
        return await super().get_response(path, scope)
