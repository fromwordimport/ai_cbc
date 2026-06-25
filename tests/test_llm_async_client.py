"""Tests for LLM async client path."""

import httpx
import pytest

from aicbc.llm.client import LLMClient


@pytest.mark.asyncio
async def test_llm_client_has_async_client() -> None:
    client = LLMClient()
    async_client = client._get_async_client()
    assert isinstance(async_client, httpx.AsyncClient)
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_async_does_not_block_event_loop() -> None:
    client = LLMClient()
    # Without a real API key this will raise, but it should fail on auth/network,
    # not on "no running event loop" or thread-pool exhaustion.
    with pytest.raises(Exception):
        await client.generate_async(messages=[{"role": "user", "content": "hello"}])
