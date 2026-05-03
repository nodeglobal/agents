"""
Memory client — delegates to local SQLite backend.
Maintains the same interface so no other code needs to change.
"""

import logging
from typing import Optional, List

from railway.memory.local_memory import (
    add_memory,
    search_memory,
    get_all_for_project,
    log_agent_update,
    VALID_PROJECTS,
)

logger = logging.getLogger(__name__)

# Re-export everything so existing imports still work
__all__ = ['add_memory', 'search_memory', 'get_all_for_project', 'log_agent_update', 'VALID_PROJECTS']
