"""Smoke-test a deployed Bobbeori MCP endpoint with a real OAuth access token."""

from __future__ import annotations

import argparse
import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def smoke_test(mcp_url: str, access_token: str) -> None:
    mcp_url = mcp_url.rstrip("/")
    resource_metadata_url = mcp_url.removesuffix("/mcp") + "/.well-known/oauth-protected-resource/mcp"

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        metadata_response = await client.get(resource_metadata_url)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        if metadata.get("resource") != mcp_url:
            raise RuntimeError("Protected resource metadata does not match the MCP URL")

        unauthorized = await client.post(mcp_url, json={})
        if unauthorized.status_code != 401 or "resource_metadata=" not in unauthorized.headers.get(
            "www-authenticate", ""
        ):
            raise RuntimeError("MCP endpoint did not return the OAuth discovery challenge")

    async with streamablehttp_client(
        mcp_url,
        headers={"Authorization": f"Bearer {access_token}"},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            if not tools.tools:
                raise RuntimeError("Authenticated MCP session returned no tools")
            print(f"OAuth smoke test passed: {len(tools.tools)} tools")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-url", required=True, help="Example: https://mcp.example.com/mcp")
    parser.add_argument("--access-token", required=True)
    args = parser.parse_args()
    asyncio.run(smoke_test(args.mcp_url, args.access_token))


if __name__ == "__main__":
    main()
