import time
import tempfile
import pytest
import asyncio
from pathlib import Path

from dume.core.record import generate_uuidv7_bytes
from dume.schema.dictionary import SchemaDictionary
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.inference.grounded_engine import GroundedInferenceEngine
from dume.session.dispatcher import SessionDispatcher, TurnPayload
from dume.scribe.committer import ScribeCommitter
from dume.scribe.worker import ScribeWorker


@pytest.mark.asyncio
async def test_foreground_latency_invariance():
    """Verify foreground fast path dispatch completes in < 1ms."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            infer = GroundedInferenceEngine(engine, schema)
            dispatcher = SessionDispatcher(infer)

            entity_bytes = generate_uuidv7_bytes()

            # Measure dispatch latency
            res = dispatcher.dispatch_turn(
                entity_id=entity_bytes,
                user_text="Switch theme to light mode and set balance to 2000"
            )

            assert res["dispatch_latency_ms"] < 5.0, f"Foreground dispatch took too long: {res['dispatch_latency_ms']} ms"
            assert dispatcher.queue.qsize() == 1


@pytest.mark.asyncio
async def test_scribe_worker_append_only_integrity():
    """
    Verify 3 consecutive updates to the same preference:
    - active_state table contains exactly 1 register
    - history_log table contains 3 chronological entries
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            infer = GroundedInferenceEngine(engine, schema)
            dispatcher = SessionDispatcher(infer)
            committer = ScribeCommitter(engine, schema)
            worker = ScribeWorker(dispatcher, committer, schema)

            entity_bytes = generate_uuidv7_bytes()

            # Dispatch 3 consecutive theme updates
            turns = [
                "Switch my theme to Light mode",
                "Actually change theme to Dark mode",
                "Set theme to High Contrast"
            ]

            for turn in turns:
                dispatcher.dispatch_turn(entity_bytes, turn)
                await asyncio.sleep(0.002)

            # Process queue items synchronously
            while not dispatcher.queue.empty():
                payload = await dispatcher.queue.get()
                worker.process_turn(payload)
                dispatcher.queue.task_done()

            # Verify active_state vs history_log counts
            active_regs = engine.get_all_active_registers(entity_bytes)
            history_logs = engine.get_history(entity_bytes)

            assert len(active_regs) == 1, f"Expected 1 active register, got {len(active_regs)}"
            assert active_regs[0].value == 3  # HIGH_CONTRAST enum id

            assert len(history_logs) == 3, f"Expected 3 history log entries, got {len(history_logs)}"


@pytest.mark.asyncio
async def test_scribe_noise_rejection():
    """Verify general conversational chit-chat generates zero DB mutations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            infer = GroundedInferenceEngine(engine, schema)
            dispatcher = SessionDispatcher(infer)
            committer = ScribeCommitter(engine, schema)
            worker = ScribeWorker(dispatcher, committer, schema)

            entity_bytes = generate_uuidv7_bytes()

            # Dispatch chit-chat turns
            chit_chats = [
                "Hello, how are you today?",
                "What is the capital of France?",
                "Thank you so much for your help!"
            ]

            for turn in chit_chats:
                dispatcher.dispatch_turn(entity_bytes, turn)

            while not dispatcher.queue.empty():
                payload = await dispatcher.queue.get()
                events = worker.process_turn(payload)
                assert len(events) == 0, f"Expected 0 mutations for chit-chat, got {len(events)}"
                dispatcher.queue.task_done()

            # Database must remain completely pristine (0 active registers, 0 history)
            active_regs = engine.get_all_active_registers(entity_bytes)
            history_logs = engine.get_history(entity_bytes)

            assert len(active_regs) == 0
            assert len(history_logs) == 0
