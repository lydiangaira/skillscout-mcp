import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            calls = [
                ("count_postings_by_company", {"skill": "python", "top_n": 3}),
                ("search_postings_by_skill", {"skill": "rust", "limit": 2}),
                ("search_postings_by_skill", {"skill": "pyhton"}),
                ("search_postings_by_skill", {"skill": "python", "limit": 99}),
            ]
            for name, args in calls:
                result = await session.call_tool(name, args)
                text = result.content[0].text if result.content else ""
                print(f"\n> {name}({args})  isError={result.is_error}")
                print(text[:600])

asyncio.run(main())