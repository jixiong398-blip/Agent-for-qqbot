"""Contracts for the Hermes-independent Soyo social-state slice."""

from soyo.social import ConversationMessage, ConversationState, EpisodeState


def test_scene_state_assigns_watermarks_and_keeps_message_lookup():
    clock = [100.0]
    state = ConversationState("agent:soyo:qq:group:fixture", now_fn=lambda: clock[0])

    first = state.append_message(ConversationMessage(message_id="m1", text="第一条"))
    second = state.append_message(ConversationMessage(message_id="m2", text="第二条"))

    assert (first.seq, second.seq) == (1, 2)
    assert state.last_user_seq == 2
    assert state.latest_user_message() is second
    assert state.lookup_message("m1") is first
    assert [item.text for item in state.snapshot()] == ["第一条", "第二条"]


def test_reply_then_three_silent_observations_quiet_and_advance_epoch():
    state = ConversationState("qq:group:fixture", now_fn=lambda: 100.0)
    state.append_message(ConversationMessage(message_id="m1", text="叫我"))

    state.record_reply("我在")
    assert state.is_attentive()
    assert state.is_episode_active()

    state.record_silent()
    state.record_silent()
    state.record_silent()

    assert not state.is_attentive()
    assert not state.is_episode_active()
    assert state.decision_epoch == 1
    assert state.quiet_since_seq == 1


def test_episode_state_round_trip_accepts_legacy_field_names():
    state = EpisodeState.from_dict(
        {
            "episode_status": "active",
            "soyo_moves": ["answer"],
            "episode_phase": "mid",
            "exiting_streak": 2,
        }
    )

    restored = EpisodeState.from_dict(state.to_dict())
    assert restored.status == "active"
    assert restored.bot_moves == ["answer"]
    assert restored.episode_phase == "mid"
    assert restored.exiting_streak == 2
