import asyncio
from pathlib import Path
import sys
import unittest

class ProtocolTests(unittest.TestCase):
    def test_official_sdk_interoperability(self):
        async def check():
            from mcp import ClientSession,StdioServerParameters
            from mcp.client.stdio import stdio_client
            server=Path(__file__).resolve().parents[1]/"scripts/server.py"
            async with stdio_client(StdioServerParameters(command=sys.executable,args=["-u",str(server)])) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    init=await session.initialize()
                    self.assertEqual(init.server_info.name,"cell-ppt-edited")
                    listing=await session.list_tools()
                    self.assertEqual(len(listing.tools),11)
                    result=await session.call_tool("cell_ppt_edited_status",{})
                    self.assertFalse(result.is_error)
                    self.assertTrue(result.structured_content["persistent"])
                    caps=await session.call_tool("cell_ppt_edited_capabilities",{})
                    self.assertEqual(len(caps.structured_content['actions']),7)
                    invalid=await session.call_tool("cell_ppt_edited_edit",{"session_id":"missing"})
                    self.assertTrue(invalid.is_error)
        asyncio.run(check())

if __name__=="__main__":unittest.main()
