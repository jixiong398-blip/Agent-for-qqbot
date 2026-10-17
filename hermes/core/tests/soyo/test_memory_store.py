"""Contracts for the first Hermes-independent Soyo memory slice."""

import pytest

from soyo.memory import SoyoMemoryStore


def test_store_requires_an_explicit_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="absolute db_path"):
        SoyoMemoryStore("relative/memory.sqlite3")


def test_exact_fact_upsert_preserves_sources_and_reopens(tmp_path):
    db_path = tmp_path / "soyo" / "memory.sqlite3"
    with SoyoMemoryStore(db_path) as store:
        fact_id = store.upsert_fact(
            category="self",
            key="preferred_name",
            value="Soyo",
            confidence=0.2,
            source_session_ids=["session-a"],
            source_context="probe",
        )
        assert store.upsert_fact(
            category="self",
            key="preferred_name",
            value="Soyo",
            confidence=0.9,
            source_session_ids=["session-b"],
        ) == fact_id

    with SoyoMemoryStore(db_path) as reopened:
        fact = reopened.get_fact(category="self", key="preferred_name")
        assert fact is not None
        assert fact.value == "Soyo"
        assert fact.confidence == 0.9
        assert fact.source_session_ids == ["session-a", "session-b"]
        assert reopened.get_fact(category="self", key="missing") is None


def test_session_turns_round_trip_in_turn_order(tmp_path):
    with SoyoMemoryStore(tmp_path / "memory.sqlite3") as store:
        store.append_turn(session_id="s1", turn_index=2, role="assistant", content="答复")
        store.append_turn(session_id="s1", turn_index=1, role="user", content="问题")
        store.append_turn(session_id="s2", turn_index=1, role="user", content="另一个会话")

        turns = store.get_session_turns("s1")
        assert [turn.content for turn in turns] == ["问题", "答复"]
        assert store.get_session_turns("s2")[0].content == "另一个会话"
        assert store.get_session_turns("s1", limit=0) == []
