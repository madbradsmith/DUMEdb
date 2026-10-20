import time
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, Union, List

from dume.core.record import uuid_to_hex, hex_to_uuid_bytes
from dume.inference.grounded_engine import GroundedInferenceEngine
from dume.session.context_manager import BoundedBufferManager, TurnEntry


@dataclass
class TurnPayload:
    entity_id: str
    user_text: str
    agent_text: str
    timestamp: int


class SessionDispatcher:
    """
    Session Stream Splitter & Bounded Context Dispatcher.
    Splits conversational turns into:
    1. Foreground Fast Path (immediate register context return & bounded scratchpad history for streaming LLM)
    2. Background Async Queue (out-of-band extraction & persistence)
    """
    def __init__(
        self,
        inference_engine: GroundedInferenceEngine,
        queue_maxsize: int = 1000,
        max_turns: int = 4,
        max_tokens: int = 2048
    ):
        self.inference_engine = inference_engine
        self.queue_maxsize = queue_maxsize
        self._queue: Optional[asyncio.Queue[TurnPayload]] = None
        self._queue_loop: Optional[asyncio.AbstractEventLoop] = None
        self.context_manager = BoundedBufferManager(max_turns=max_turns, max_tokens=max_tokens)

    @property
    def queue(self) -> asyncio.Queue[TurnPayload]:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._queue is None or (current_loop is not None and self._queue_loop != current_loop):
            self._queue = asyncio.Queue(maxsize=self.queue_maxsize)
            self._queue_loop = current_loop
        return self._queue

    def dispatch_turn(
        self,
        entity_id: Union[bytes, str],
        user_text: str,
        agent_text: str = ""
    ) -> Dict[str, Any]:
        """
        Foreground Fast Path:
        1. Immediately queries active registers from DUMEdb (O(1) mmap read).
        2. Evaluates rolling scratchpad buffer & applies eviction policies (SLIDING_WINDOW / WATERMARK).
        3. Pushes payload onto async queue with zero disk/lock wait.
        4. Returns register context & bounded scratchpad slice for immediate streaming synthesis.
        """
        t0 = time.perf_counter()
        
        entity_str = uuid_to_hex(entity_id) if isinstance(entity_id, bytes) else entity_id
        timestamp = int(time.time()) & 0xFFFFFFFF

        # 1. Fetch active registers for prompt context
        register_ctx = self.inference_engine.build_register_context(entity_str)

        # 2. Process turn through BoundedBufferManager
        bounded_history = self.context_manager.add_turn(
            entity_id=entity_str,
            user_text=user_text,
            agent_text=agent_text,
            timestamp=timestamp
        )
        scratchpad_summary = self.context_manager.get_scratchpad_summary(entity_str)

        # 3. Asynchronously push to background scribe queue (Non-blocking)
        payload = TurnPayload(
            entity_id=entity_str,
            user_text=user_text,
            agent_text=agent_text,
            timestamp=timestamp
        )
        
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

        t1 = time.perf_counter()
        dispatch_latency_ms = (t1 - t0) * 1000

        return {
            "entity_id": entity_str,
            "register_context": register_ctx,
            "bounded_history": bounded_history,
            "scratchpad_summary": scratchpad_summary,
            "dispatch_latency_ms": dispatch_latency_ms,
            "queue_size": self.queue.qsize()
        }

    def update_agent_response(self, entity_id: str, agent_text: str):
        """Updates agent_text of the last turn in scratchpad once LLM completion finishes."""
        entity_str = uuid_to_hex(entity_id) if isinstance(entity_id, bytes) else entity_id
        self.context_manager.update_last_turn_agent_text(entity_str, agent_text)

    def flush_scratchpad(self, entity_id: Union[bytes, str]) -> Dict[str, Any]:
        """Flushes in-memory scratchpad buffer for target entity without touching LMDB registers."""
        entity_str = uuid_to_hex(entity_id) if isinstance(entity_id, bytes) else entity_id
        return self.context_manager.flush_session_scratchpad(entity_str)
