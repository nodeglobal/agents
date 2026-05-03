import os
import httpx
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

DISCORD_API = 'https://discord.com/api/v10'


class DiscordNotifier:
    def __init__(self):
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN', '')
        self.channel_id = os.getenv('DISCORD_CHANNEL_ID', '')
        if not self.bot_token or not self.channel_id:
            logger.warning('Discord credentials not set — notifications disabled')

    async def send(self, message: str) -> bool:
        if not self.bot_token or not self.channel_id:
            logger.info(f'[DISCORD DISABLED] {message[:100]}')
            return False

        # Discord message limit is 2000 chars
        if len(message) > 2000:
            message = message[:1997] + '...'

        headers = {
            'Authorization': f'Bot {self.bot_token}',
            'Content-Type': 'application/json',
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f'{DISCORD_API}/channels/{self.channel_id}/messages',
                    headers=headers,
                    json={'content': message}
                )
                if resp.status_code in (200, 201):
                    logger.info(f'Discord sent: {message[:80]}')
                    return True
                else:
                    logger.error(f'Discord failed: {resp.status_code} {resp.text[:200]}')
                    return False
        except Exception as e:
            logger.error(f'Discord error: {e}')
            return False

    async def send_spec_brief(self, thread_id: str, project: str, brief: str, complexity: str) -> bool:
        brief_preview = brief[:800] + '...' if len(brief) > 800 else brief
        return await self.send(
            f"📋 **Spec Brief — {project.upper()} [{complexity}]**\n"
            f"Thread: `{thread_id[:8]}`\n\n"
            f"{brief_preview}\n\n"
            f"Reply with corrections or approve via API."
        )

    async def send_task_complete(self, thread_id: str, project: str, score: int, files: List[str]) -> bool:
        files_str = ', '.join(files[:5]) + (f' +{len(files)-5} more' if len(files) > 5 else '')
        return await self.send(
            f"✅ **Task Complete — {project.upper()} [{score}/100]**\n"
            f"Thread: `{thread_id[:8]}`\n"
            f"Files: {files_str or 'none'}"
        )

    async def send_escalation(self, thread_id: str, project: str, failure_summary: str) -> bool:
        return await self.send(
            f"🚨 **ESCALATION — {project.upper()} — 3 Attempts Failed**\n"
            f"Thread: `{thread_id[:8]}`\n\n"
            f"{failure_summary[:500]}\n\n"
            f"Manual intervention required."
        )

    async def send_question(self, thread_id: str, question: str, project: str) -> bool:
        return await self.send(
            f"❓ **Claude Code Question — {project.upper()}**\n"
            f"Thread: `{thread_id[:8]}`\n\n"
            f"{question}"
        )

    async def send_daily_summary(self, summary: dict) -> bool:
        return await self.send(
            f"📊 **DeltaNode Daily Summary**\n"
            f"Tasks completed: {summary.get('completed', 0)}\n"
            f"Avg score: {summary.get('avg_score', 0):.0f}/100\n"
            f"Escalations: {summary.get('escalations', 0)}\n"
            f"M2: {summary.get('m2_uptime', 'discord')}\n"
            f"Queue: {summary.get('queue_length', 0)} pending"
        )

    async def send_update_report(self, summary: str) -> bool:
        return await self.send(
            f"🔄 **Update Agent Weekly Report**\n\n"
            f"{summary[:1500]}"
        )


notifier = DiscordNotifier()
