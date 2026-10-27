"""MCP server exposing the same four tools, so Claude Desktop (or any MCP client) can query the warehouse.

    python mcp_entry.py            stdio (default; what Claude Desktop launches)
    python mcp_entry.py --http     streamable HTTP
No Gemini key is needed: the MCP client's own model does the reasoning, these are just the tools.
Uses the MCP Python SDK 2.x API (`MCPServer`; in 1.x this class was `FastMCP`).
stdout is the protocol channel under stdio - never print() in here.
"""
from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer

from .config import Settings
from .tools import SchemaTools, build_tools

INSTRUCTIONS = (
    "Read-only access to a marketing analytics warehouse (Meta Ads + Shopify, amounts in INR). "
    "Workflow: search_schema -> get_schema -> run_sql (one SELECT) -> explain_result. Only use tables "
    "and columns returned by get_schema. Compute CTR/CPC/CPM/ROAS/ROI from SUMs with NULLIF; never "
    "use fact_ads.ctr/cpm/cpc/roi (averages of ratios). dim_date.month is an integer 1-12."
)


def create_server(tools: SchemaTools | None = None) -> MCPServer:
    tools = tools or build_tools(Settings())
    mcp = MCPServer("marketing-analytics", instructions=INSTRUCTIONS)

    @mcp.tool()
    def search_schema(question: str, top_k: int = 3) -> dict:
        """Find the tables most relevant to a business question (semantic search over table and column descriptions)."""
        return tools.search_schema(question, top_k)

    @mcp.tool()
    def get_schema(tables: list[str]) -> dict:
        """Get columns, types, keys, descriptions and sample values for the given tables."""
        return tools.get_schema(tables)

    @mcp.tool()
    def run_sql(sql: str) -> dict:
        """Run ONE read-only SELECT query. Errors are returned so you can fix the query and retry."""
        return tools.run_sql(sql)

    @mcp.tool()
    def explain_result() -> dict:
        """Profile the most recent run_sql result: row count, numeric stats and top text values."""
        return tools.explain_result()

    return mcp


def main() -> None:
    create_server().run("streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
