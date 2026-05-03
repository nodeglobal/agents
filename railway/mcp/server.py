import os
import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

BASE_URL = os.getenv('AGENT_BASE_URL', 'http://localhost:8000')
server = Server('deltanode-agents')

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name='run_task',
            description='Submit a task to the DeltaNode 5-agent stack. Returns spec brief for approval.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'task': {'type': 'string', 'description': 'The task to execute'},
                    'project': {
                        'type': 'string',
                        'description': 'Project name — matches directory in your workspace',
                        'default': 'general'
                    }
                },
                'required': ['task']
            }
        ),
        Tool(
            name='approve_task',
            description='Approve a spec brief. Returns immediately — pipeline runs in background. Poll task_status for progress.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'thread_id': {'type': 'string'},
                    'corrections': {'type': 'string', 'description': 'Optional corrections to the spec brief'}
                },
                'required': ['thread_id']
            }
        ),
        Tool(
            name='task_status',
            description='Check current status of a task. Returns stage, progress, and results when complete.',
            inputSchema={
                'type': 'object',
                'properties': {'thread_id': {'type': 'string'}},
                'required': ['thread_id']
            }
        ),
        Tool(
            name='cancel_task',
            description='Cancel a pending or running task.',
            inputSchema={
                'type': 'object',
                'properties': {'thread_id': {'type': 'string'}},
                'required': ['thread_id']
            }
        ),
        Tool(
            name='trigger_update',
            description='Trigger the Update Agent to scan for stack changes.',
            inputSchema={'type': 'object', 'properties': {}, 'required': []}
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    timeout = 30.0  # All endpoints now return fast
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if name == 'run_task':
                r = await client.post(f'{BASE_URL}/task',
                    json={'task': arguments['task'], 'project': arguments.get('project','general')})
                d = r.json()
                return [TextContent(type='text', text=
                    f"✅ Task submitted\nThread: {d['thread_id']}\n"
                    f"Project: {d['project']} | Complexity: {d.get('complexity','Medium')}\n\n"
                    f"SPEC BRIEF:\n{d.get('spec_brief','N/A')}\n\n"
                    f"Approve: approve_task(thread_id='{d['thread_id']}')\n"
                    f"Check: task_status(thread_id='{d['thread_id']}')"
                )]

            elif name == 'approve_task':
                body = {}
                if arguments.get('corrections'):
                    body['corrections'] = arguments['corrections']
                r = await client.post(f"{BASE_URL}/approve/{arguments['thread_id']}", json=body)
                d = r.json()
                return [TextContent(type='text', text=
                    f"✅ Approved — pipeline running in background\n"
                    f"Thread: {d.get('thread_id')}\n"
                    f"Status: {d.get('status')}\n\n"
                    f"Poll progress: task_status(thread_id='{arguments['thread_id']}')"
                )]

            elif name == 'task_status':
                r = await client.get(f"{BASE_URL}/status/{arguments['thread_id']}")
                if r.status_code == 404:
                    return [TextContent(type='text', text=f"Task {arguments['thread_id']} not found.")]
                d = r.json()
                status = d.get('status', 'unknown')
                stage = d.get('stage', 'unknown')
                result = d.get('result')

                lines = [
                    f"Thread: {d.get('thread_id')}",
                    f"Status: {status}",
                    f"Stage: {stage}",
                    f"Project: {d.get('project', 'unknown')}",
                    f"Complexity: {d.get('complexity', 'unknown')}",
                ]

                if d.get('error'):
                    lines.append(f"Error: {d['error']}")

                if result:
                    lines.append(f"\n--- RESULT ---")
                    lines.append(f"Score: {result.get('validation_score', 0)}/100")
                    lines.append(f"Approved: {'✅' if result.get('approved') else '❌'}")
                    lines.append(f"Tests: {'✅' if result.get('tests_passed') else '❌'}")
                    lines.append(f"Iterations: {result.get('iterations', 0)}")
                    lines.append(f"Files: {', '.join(result.get('files_changed', []) or ['none'])}")
                    lines.append(f"M2 Session: {result.get('m2_session_id', 'N/A')}")
                    if result.get('build_output'):
                        lines.append(f"\nOUTPUT:\n{result['build_output'][:2000]}")
                    if result.get('validation_notes'):
                        lines.append(f"\nVALIDATION:\n{result['validation_notes'][:500]}")

                return [TextContent(type='text', text='\n'.join(lines))]

            elif name == 'cancel_task':
                r = await client.post(f"{BASE_URL}/reject/{arguments['thread_id']}")
                return [TextContent(type='text', text=f"Task {arguments['thread_id']} cancelled.")]

            elif name == 'trigger_update':
                r = await client.post(f'{BASE_URL}/update/trigger')
                return [TextContent(type='text', text=f"Update Agent triggered. {r.json().get('message','')}")]

        except httpx.TimeoutException:
            return [TextContent(type='text', text=f'Error: Request timed out after {timeout}s')]
        except Exception as e:
            return [TextContent(type='text', text=f'Error: {str(e)}')]

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == '__main__':
    asyncio.run(main())
