from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    server_cmd = StdioServerParameters(
        command=sys.executable,
        args=["-m", "route_planner_mcp.server"],
        cwd=None,
    )

    async with stdio_client(server_cmd) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            # Warm the tool registry so unknown tool names surface early.
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            if tool_name not in tool_names:
                available = ", ".join(sorted(tool_names)) or "<none>"
                raise SystemExit(f"Unknown tool '{tool_name}'. Server exposes: {available}")

            result = await session.call_tool(tool_name, arguments)
            return result.model_dump(mode="json")


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return anyio.run(_call_tool, tool_name, arguments)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call a Route Planner MCP tool without managing JSON-RPC plumbing."
    )
    parser.add_argument("tool", help="Tool name, e.g. nav.route, nav.risk_eval, nav.export.")
    parser.add_argument(
        "--args",
        default="{}",
        help="JSON dictionary containing the arguments for the tool (default: {}).",
    )

    args = parser.parse_args()
    try:
        arguments = json.loads(args.args)
    except json.JSONDecodeError as exc:  # noqa: BLE001
        raise SystemExit(f"Invalid JSON for --args: {exc}") from exc

    response = call_tool(args.tool, arguments)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()

