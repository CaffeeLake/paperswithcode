"""Explicit CI-only image publication entry point.

This is never imported or called by the web service. The emitted immutable image
ID is copied into a later staging release manifest before allocation is enabled.
"""

import asyncio

import modal

from backend.chat_sandbox_worker.contract import IMAGE_PUBLISH_NAME, MODAL_APP_NAME
from backend.chat_sandbox_worker.image import app, image


async def _publish() -> str:
    await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=True)
    async with app.run.aio():
        built = await image.build.aio(app)
        await built.publish.aio(IMAGE_PUBLISH_NAME)
        if not built.object_id:
            raise RuntimeError("Modal image publication returned no immutable image ID")
        return built.object_id


def main() -> int:
    print(asyncio.run(_publish()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
