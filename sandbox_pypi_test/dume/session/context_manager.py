import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class TurnEntry:
    user_text: str
    agent_text: str
    timestamp: int
    token_estimate: int = 0

    def __post_init__(self):
        if not self.token_estimate:
            # Token estimate heuristic: ~4 chars per token
            total_chars = len(self.user_text) + len(self.agent_text)
            self.token_estimate = max(1, total_chars // 4)


class BoundedBufferManager:
    """
    Bounded Context Buffer Manager.
    Enforces sliding window eviction and token watermark ceilings on ephemeral session scratchpads.
    Prevents context bloat while keeping DUMEdb discrete registers intact.
    """
    def __init__(
        self,
        max_turns: int = 4,
        max_tokens: int = 2048,
        policy: str = "SLIDING_WINDOW"
    ):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.policy = policy
        # Ephemeral scratchpad buffer per entity: {entity_id: [TurnEntry, ...]}
        self.buffers: Dict[str, List[TurnEntry]] = {}

    def add_turn(
        self,
        entity_id: str,
        user_text: str,
        agent_text: str = "",
        timestamp: Optional[int] = None
    ) -> List[TurnEntry]:
        """
        Appends a new turn payload to the entity's scratchpad buffer and applies eviction policy.
        Returns the updated bounded TurnEntry list for the entity.
        """
        ts = timestamp if timestamp is not None else int(time.time())
        entry = TurnEntry(user_text=user_text, agent_text=agent_text, timestamp=ts)

        if entity_id not in self.buffers:
            self.buffers[entity_id] = []

        buffer = self.buffers[entity_id]
        buffer.append(entry)

        # Policy 1: SLIDING_WINDOW Eviction (Keeps at most max_turns)
        while len(buffer) > self.max_turns:
            buffer.pop(0)

        # Policy 2: TOKEN_WATERMARK_FLUSH Eviction
        total_tokens = sum(t.token_estimate for t in buffer)
        while total_tokens > self.max_tokens and len(buffer) > 1:
            evicted = buffer.pop(0)
            total_tokens -= evicted.token_estimate

        return list(buffer)

    def update_last_turn_agent_text(self, entity_id: str, agent_text: str):
        """Updates the agent_text of the most recent turn once LLM synthesis completes."""
        buffer = self.buffers.get(entity_id, [])
        if buffer:
            last = buffer[-1]
            last.agent_text = agent_text
            total_chars = len(last.user_text) + len(agent_text)
            last.token_estimate = max(1, total_chars // 4)

    def get_bounded_history(self, entity_id: str) -> List[TurnEntry]:
        """Returns current in-memory turn list for the given entity."""
        return list(self.buffers.get(entity_id, []))

    def flush_session_scratchpad(self, entity_id: str) -> Dict[str, Any]:
        """
        Explicitly clears the conversational scratchpad buffer for the entity.
        Does NOT modify DUMEdb active registers or history audit log.
        """
        prev_count = len(self.buffers.get(entity_id, []))
        self.buffers[entity_id] = []
        return {
            "entity_id": entity_id,
            "flushed_turns": prev_count,
            "scratchpad_active_turns": 0,
            "max_turns": self.max_turns
        }

    def get_scratchpad_summary(self, entity_id: str) -> Dict[str, Any]:
        """Returns turn count, token estimate, and budget metrics for the entity's scratchpad."""
        buffer = self.buffers.get(entity_id, [])
        est_tokens = sum(t.token_estimate for t in buffer)
        return {
            "entity_id": entity_id,
            "active_turns": len(buffer),
            "max_turns": self.max_turns,
            "estimated_tokens": est_tokens,
            "max_tokens": self.max_tokens,
            "policy": self.policy
        }
