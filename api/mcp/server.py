"""MCP (Model Context Protocol) server — exposes BrainC tools via a standard interface.

Implements the minimal MCP surface:
  GET  /mcp/tools    — list available tools with JSON schemas
  POST /mcp/call     — dispatch a tool call and return its result
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.tools.executor import execute_code
from api.tools.file_reader import read_file
from api.tools.search import search

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Tool definitions (MCP schema format) ─────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "braincbrain_search",
        "description": "Search the web using the local SearXNG instance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "braincbrain_execute",
        "description": (
            "Execute Python code in a sandboxed subprocess. "
            "Dangerous imports and file writes are blocked."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "braincbrain_read_file",
        "description": (
            "Read a file from the BrainC workspace directory (~BrainC/workspace/). "
            "Supported extensions: .txt .md .py .js .json .csv .yaml .yml .html .css"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path inside the workspace",
                },
            },
            "required": ["path"],
        },
    },
]


# ── Request model ─────────────────────────────────────────────────────────────


class McpCallRequest(BaseModel):
    name: str
    arguments: dict = {}


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/tools")
async def mcp_list_tools():
    """Return the list of available MCP tools."""
    return {"tools": _TOOLS}


@router.post("/call")
async def mcp_call_tool(req: McpCallRequest):
    """Dispatch a tool call and return its result."""
    name = req.name
    args = req.arguments

    if name == "braincbrain_search":
        query = args.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="'query' argument is required")
        num_results = int(args.get("num_results", 5))
        results = await search(query, num_results=num_results)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(results, ensure_ascii=False, indent=2),
                }
            ]
        }

    if name == "braincbrain_execute":
        code = args.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="'code' argument is required")
        result = await asyncio.to_thread(execute_code, code)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ]
        }

    if name == "braincbrain_read_file":
        path = args.get("path")
        if not path:
            raise HTTPException(status_code=400, detail="'path' argument is required")
        result = await read_file(path)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ]
        }

    raise HTTPException(status_code=404, detail=f"Unknown tool: {name!r}")
