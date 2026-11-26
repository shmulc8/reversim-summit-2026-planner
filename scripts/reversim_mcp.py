#!/usr/bin/env python3
"""Small, dependency-free HTTP MCP client for the public Reversim 2026 server."""

import argparse
import json
import sys
import urllib.error
import urllib.request


ENDPOINT = "https://summit2026.reversim.com/mcp"
VERSION = "2025-06-18"


def request(method, request_id=None, params=None, session=None):
    message = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": VERSION,
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(ENDPOINT, data=json.dumps(message).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8")
        session = response.headers.get("Mcp-Session-Id", session)
        content_type = response.headers.get("Content-Type", "")
    if not body:
        return None, session
    if "text/event-stream" in content_type:
        events = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
        if not events:
            raise ValueError("MCP server returned no data event")
        body = events[-1]
    payload = json.loads(body)
    if "error" in payload:
        raise ValueError(f"MCP error: {payload['error']}")
    return payload.get("result"), session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tools", help="List live MCP tool names and input schemas")
    call = sub.add_parser("call", help="Call a live MCP tool")
    call.add_argument("tool", help="MCP tool name")
    call.add_argument("arguments", help="JSON object of tool arguments")
    args = parser.parse_args()

    result, session = request("initialize", 1, {
        "protocolVersion": VERSION,
        "capabilities": {},
        "clientInfo": {"name": "reversim-skill-helper", "version": "1.0"},
    })
    if not result or not session:
        raise ValueError("MCP initialization failed")
    request("notifications/initialized", session=session)

    if args.command == "tools":
        result, _ = request("tools/list", 2, session=session)
        output = result["tools"]
    else:
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
        result, _ = request("tools/call", 2,
                            {"name": args.tool, "arguments": arguments}, session=session)
        if result.get("isError"):
            raise ValueError(f"MCP tool failed: {result.get('content')}")
        content = [block["text"] for block in result.get("content", [])
                   if block.get("type") == "text"]
        output = json.loads(content[0]) if len(content) == 1 else result
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"reversim_mcp: {exc}", file=sys.stderr)
        sys.exit(1)
