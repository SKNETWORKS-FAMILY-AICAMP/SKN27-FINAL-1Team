"""Smoke-test a deployed Bobbeori MCP endpoint with a real OAuth access token."""

from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def smoke_test(mcp_url: str, access_token: str, resource_url: str | None = None) -> None:
    mcp_url = mcp_url.rstrip("/")
    expected_resource = (resource_url or mcp_url).rstrip("/")
    parsed_resource = urlparse(expected_resource)
    resource_path = parsed_resource.path.strip("/")
    resource_metadata_url = (
        f"{parsed_resource.scheme}://{parsed_resource.netloc}/.well-known/oauth-protected-resource"
        + (f"/{resource_path}" if resource_path else "")
    )

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        metadata_response = await client.get(resource_metadata_url)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        metadata_resource = str(metadata.get("resource", "")).rstrip("/")
        if metadata_resource != expected_resource:
            raise RuntimeError("Protected resource metadata does not match the expected resource URL")

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
    parser.add_argument("--resource-url", help="Expected OAuth resource. Example: https://mcp.example.com")
    parser.add_argument("--access-token", default=os.getenv("MCP_ACCESS_TOKEN"))
    args = parser.parse_args()
    if not args.access_token:
        parser.error("--access-token or MCP_ACCESS_TOKEN is required")
    asyncio.run(smoke_test(args.mcp_url, args.access_token, args.resource_url))


if __name__ == "__main__":
    main()
