"""Fixtures for infrastructure integration tests."""

from __future__ import annotations

import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _mongo_available() -> bool:
    """Check whether the configured MongoDB is reachable."""
    url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
    try:
        client: AsyncIOMotorClient = AsyncIOMotorClient(url, serverSelectionTimeoutMS=1500)
        await client.admin.command("ping")
        client.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
async def mongo_client():
    """Yield a MongoDB client (real or mocked) and drop the test database afterwards."""
    if await _mongo_available():
        url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
        client = AsyncIOMotorClient(url)
        db_name = "aicbc_test_stores"
        db = client[db_name]
        # Reset test database.
        await client.drop_database(db_name)
    else:
        # Fall back to mongomock for CI environments without MongoDB.
        from mongomock_motor import AsyncMongoMockClient

        client = AsyncMongoMockClient()
        db_name = "aicbc_test_stores"
        db = client[db_name]

    # Initialize Beanie with all document models.
    from beanie import init_beanie

    from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS

    # Patch mongomock's list_collection_names to ignore unknown kwargs
    # and patch mongomock_motor to properly await Beanie query objects.
    if not await _mongo_available():
        import mongomock

        _orig_list_collections = mongomock.database.Database.list_collection_names

        def _patched_list_collection_names(self, *args, **kwargs):
            for key in list(kwargs.keys()):
                if key not in ("session",):
                    kwargs.pop(key, None)
            return _orig_list_collections(self, *args, **kwargs)

        mongomock.database.Database.list_collection_names = _patched_list_collection_names

        # Patch _run in store_mongo to handle mongomock_motor query objects
        import aicbc.core.store_mongo as _store_mongo_module

        _orig_run = _store_mongo_module._run

        def _patched_run(awaitable):
            async def _execute():
                # Handle Beanie query objects by awaiting them
                if hasattr(awaitable, "__await__"):
                    return await awaitable
                return awaitable

            try:
                import asyncio

                asyncio.get_running_loop()
                # We're in an async context, just await directly
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _execute())
                    return future.result()
            except RuntimeError:
                return asyncio.run(_execute())

        _store_mongo_module._run = _patched_run

    await init_beanie(database=db, document_models=ALL_DOCUMENT_MODELS)

    yield client

    if await _mongo_available():
        await client.drop_database(db_name)
        client.close()


@pytest.fixture
async def clean_db(mongo_client):
    """Drop all collections before each test for isolation."""
    from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS

    db = mongo_client["aicbc_test_stores"]
    for doc_model in ALL_DOCUMENT_MODELS:
        await db[doc_model.Settings.name].delete_many({})
