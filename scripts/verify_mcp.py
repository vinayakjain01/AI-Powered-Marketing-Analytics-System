"""End-to-end check of the MCP server with a real client session over stdio.

Launches mcp_entry.py as a subprocess from a DIFFERENT working directory (like Claude Desktop
does), then: initialize -> list_tools -> call search_schema / run_sql / a blocked write.
    python scripts/verify_mcp.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ENTRY = Path(__file__).resolve().parents[1] / "mcp_entry.py"


def text_of(result) -> dict:
    return json.loads(result.content[0].text) if result.content else {}


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(ENTRY)], cwd=tempfile.gettempdir())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"initialize ok: server={init.server_info.name}")
            tools = await session.list_tools()
            print("list_tools:", [t.name for t in tools.tools])

            found = text_of(await session.call_tool("search_schema", {"question": "total ad spend by region"}))
            print("search_schema ->", [(t["table"], t["score"]) for t in found["tables"]])

            sql = ("SELECT c.geo_location_segment AS region, ROUND(SUM(f.amount_spent)) AS spend, "
                   "ROUND(SUM(f.purchase_value) / NULLIF(SUM(f.amount_spent), 0), 2) AS roas "
                   "FROM fact_ads f JOIN dim_campaign c ON c.campaign_id = f.campaign_id "
                   "GROUP BY 1 ORDER BY spend DESC")
            res = text_of(await session.call_tool("run_sql", {"sql": sql}))
            print("run_sql ok:", res["ok"], "| columns:", res["columns"])
            for row in res["rows"]:
                print("   ", row)

            blocked = text_of(await session.call_tool("run_sql", {"sql": "DELETE FROM fact_ads"}))
            print("write attempt ->", blocked["error"])
            profile = text_of(await session.call_tool("explain_result", {}))
            print("explain_result rows:", profile["row_count"])


if __name__ == "__main__":
    asyncio.run(main())
