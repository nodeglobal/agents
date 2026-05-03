import os
import uuid
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from graph.main_graph import agent_graph
from agents.update_agent import run_update_agent
from agents.self_improve_agent import run_self_improve
from notifications.discord import notifier
from memory.mem0_client import add_memory, search_memory
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

daily_stats = {'completed':0,'escalations':0,'new_memories':0,'avg_scores':[]}
task_tracker = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(run_update_agent, 'cron', day_of_week='sun', hour=9, minute=0)
    scheduler.add_job(run_self_improve, 'cron', day_of_week='wed', hour=10, minute=0)
    summary_hour = int(os.getenv('DAILY_SUMMARY_HOUR', 6))
    summary_minute = int(os.getenv('DAILY_SUMMARY_MINUTE', 0))
    scheduler.add_job(send_daily_summary, 'cron', hour=summary_hour, minute=summary_minute)
    scheduler.start()
    logger.info('DeltaNode Dev Agents v5.0.0 started — Dashboard at http://localhost:%s', os.getenv('PORT', 8000))
    yield
    scheduler.shutdown()

app = FastAPI(title='DeltaNode Dev Agents', version='5.0.0', lifespan=lifespan)

static_dir = Path(__file__).parent / 'static'
if static_dir.exists():
    app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')

async def send_daily_summary():
    avg_score = sum(daily_stats['avg_scores']) / len(daily_stats['avg_scores']) if daily_stats['avg_scores'] else 0
    await notifier.send_daily_summary({
        'completed': daily_stats['completed'],
        'avg_score': avg_score,
        'escalations': daily_stats['escalations'],
        'new_memories': daily_stats['new_memories'],
        'm2_uptime': 'local',
        'update_status': 'idle',
        'queue_length': 0
    })
    daily_stats.update({'completed':0,'escalations':0,'new_memories':0,'avg_scores':[]})

class TaskRequest(BaseModel):
    task: str
    project: str = 'general'

class ApprovalRequest(BaseModel):
    corrections: Optional[str] = None

@app.get('/')
async def dashboard():
    index = static_dir / 'dashboard.html'
    if index.exists():
        return FileResponse(str(index))
    return {'message': 'DeltaNode Agents v5.0.0 — API running. Dashboard not found.'}

@app.get('/health')
async def health():
    return {'status':'ok','version':'5.0.0'}

@app.get('/tasks')
async def list_tasks():
    return [
        {
            'thread_id': tid,
            'status': info.get('status'),
            'stage': info.get('stage'),
            'project': info.get('project'),
            'complexity': info.get('complexity'),
            'created_at': info.get('created_at'),
            'spec_brief': info.get('spec_brief'),
            'error': info.get('error'),
            'result': info.get('result'),
        }
        for tid, info in sorted(task_tracker.items(), key=lambda x: x[1].get('created_at', ''), reverse=True)
    ]

@app.post('/task')
async def create_task(req: TaskRequest):
    thread_id = str(uuid.uuid4())
    config = {'configurable':{'thread_id':thread_id}}

    initial_state = {
        'raw_task':req.task, 'project':req.project,
        'spec_brief':None, 'spec_approved':False,
        'spec_clarifications':[], 'spec_complexity':'Medium',
        'context_package':None, 'memory_hits':[],
        'build_output':None, 'build_annotations':[],
        'files_changed':[], 'tests_passed':False,
        'validation_score':None, 'validation_notes':'',
        'validation_issues':[], 'approved':False,
        'iteration':0, 'thread_id':thread_id,
        'messages':[], 'error':None,
        'session_id':None
    }

    task_tracker[thread_id] = {
        'status': 'spec_running',
        'project': req.project,
        'created_at': datetime.datetime.utcnow().isoformat(),
        'result': None,
        'error': None,
    }

    try:
        result = await agent_graph.ainvoke(initial_state, config=config)
        task_tracker[thread_id]['status'] = 'awaiting_approval'
        task_tracker[thread_id]['spec_brief'] = result.get('spec_brief')
        task_tracker[thread_id]['complexity'] = result.get('spec_complexity', 'Medium')
        return {
            'thread_id':thread_id, 'status':'awaiting_approval',
            'project':req.project, 'complexity':result.get('spec_complexity','Medium'),
            'spec_brief':result.get('spec_brief'),
            'message':'Spec brief ready. Approve via /approve/{thread_id} or from the dashboard.'
        }
    except Exception as e:
        logger.error(f'Task creation failed: {e}')
        task_tracker[thread_id]['status'] = 'error'
        task_tracker[thread_id]['error'] = str(e)
        raise HTTPException(500, str(e))


async def _run_pipeline_async(thread_id: str, corrections: Optional[str] = None):
    config = {'configurable':{'thread_id':thread_id}}
    try:
        update = {'spec_approved':True}
        if corrections:
            update['spec_clarifications'] = [corrections]

        await agent_graph.aupdate_state(config, update)

        task_tracker[thread_id]['status'] = 'pipeline_running'
        task_tracker[thread_id]['stage'] = 'research'

        result = await agent_graph.ainvoke(None, config=config)

        score = result.get('validation_score', 0)
        approved = result.get('approved', False)
        iteration = result.get('iteration', 0)

        if score:
            daily_stats['avg_scores'].append(score)
        if approved:
            daily_stats['completed'] += 1
        elif iteration >= 3:
            daily_stats['escalations'] += 1

        task_tracker[thread_id]['status'] = 'approved' if approved else ('escalated' if iteration >= 3 else 'blocked')
        task_tracker[thread_id]['result'] = {
            'validation_score': score,
            'iterations': iteration,
            'files_changed': result.get('files_changed', []),
            'tests_passed': result.get('tests_passed', False),
            'build_output': result.get('build_output'),
            'validation_notes': result.get('validation_notes'),
            'build_annotations': result.get('build_annotations', []),
            'approved': approved,
        }
        task_tracker[thread_id]['stage'] = 'complete'

    except Exception as e:
        logger.error(f'Pipeline failed for {thread_id}: {e}')
        task_tracker[thread_id]['status'] = 'error'
        task_tracker[thread_id]['error'] = str(e)
        task_tracker[thread_id]['stage'] = 'error'


@app.post('/approve/{thread_id}')
async def approve_task(thread_id: str, req: ApprovalRequest = ApprovalRequest()):
    if thread_id not in task_tracker:
        task_tracker[thread_id] = {
            'status': 'awaiting_approval',
            'project': 'unknown',
            'created_at': datetime.datetime.utcnow().isoformat(),
            'result': None,
            'error': None,
        }

    task_tracker[thread_id]['status'] = 'pipeline_starting'
    task_tracker[thread_id]['stage'] = 'approving'
    task_tracker[thread_id]['approved_at'] = datetime.datetime.utcnow().isoformat()

    asyncio.create_task(_run_pipeline_async(thread_id, req.corrections))

    return {
        'thread_id': thread_id,
        'status': 'pipeline_started',
        'message': f'Pipeline running. Check status at /status/{thread_id} or on the dashboard.'
    }


@app.get('/status/{thread_id}')
async def get_task_status(thread_id: str):
    if thread_id not in task_tracker:
        raise HTTPException(404, f'Task {thread_id} not found.')

    info = task_tracker[thread_id]
    response = {
        'thread_id': thread_id,
        'status': info.get('status'),
        'stage': info.get('stage'),
        'project': info.get('project'),
        'complexity': info.get('complexity'),
        'created_at': info.get('created_at'),
        'approved_at': info.get('approved_at'),
        'error': info.get('error'),
    }

    if info.get('result'):
        response['result'] = info['result']
    if info.get('spec_brief'):
        response['spec_brief'] = info['spec_brief']

    return response


@app.post('/reject/{thread_id}')
async def reject_task(thread_id: str):
    if thread_id in task_tracker:
        task_tracker[thread_id]['status'] = 'cancelled'
        task_tracker[thread_id]['stage'] = 'cancelled'
    return {'thread_id':thread_id,'status':'cancelled'}

@app.post('/update/trigger')
async def trigger_update():
    asyncio.create_task(run_update_agent())
    return {'status':'triggered','message':'Update Agent running.'}

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT',8000))
    uvicorn.run('main:app', host='0.0.0.0', port=port, reload=False)
