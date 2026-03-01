"""MCP client — connects to external MCP servers listed in api/mcp/config.json.

Usage:
    client = McpClient()
    tools = await client.list_tools()        # aggregate tools from all enabled servers
    result = await client.call_tool(server_name, tool_name, arguments)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config() -> list[dict]:
    """Return the list of server configs (only enabled ones)."""
    if not _CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(_CONFIG_PATH.read_text())
        return [s for s in data.get("servers", []) if s.get("enabled", False)]
    except (json.JSONDecodeError, OSError):
        return []


class McpClient:
    """Thin async MCP client that fans out to all enabled external servers."""

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout

    async def list_tools(self) -> list[dict]:
        """Return all tools from all enabled MCP servers, tagged with their server name."""
        servers = _load_config()
        if not servers:
            return []

        all_tools: list[dict] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for server in servers:
                try:
                    res = await client.get(f"{server['url'].rstrip('/')}/tools")
                    if res.status_code == 200:
                        data = res.json()
                        for tool in data.get("tools", []):
                            tool = dict(tool)
                            tool["_server"] = server["name"]
                            all_tools.append(tool)
                except httpx.RequestError:
                    # Server unreachable — skip silently
                    continue

        return all_tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict:
        """Call a tool on a specific external server by server name."""
        servers = _load_config()
        server = next((s for s in servers if s["name"] == server_name), None)
        if server is None:
            return {"error": f"No enabled server named {server_name!r}"}

        url = f"{server['url'].rstrip('/')}/call"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(
                    url, json={"name": tool_name, "arguments": arguments}
                )
                if res.status_code == 200:
                    return res.json()
                return {"error": f"Server returned {res.status_code}: {res.text}"}
        except httpx.RequestError as exc:
            return {"error": f"Could not reach {server_name}: {exc}"}
