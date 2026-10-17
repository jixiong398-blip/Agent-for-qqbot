"""Exit/wake invariants retained by the staging social policy."""

from soyo.social.admission import enforce_exit_gate, reset_for_directed_message
from soyo.social.state import ConversationState


def test_exit_needs_two_observations_and_does_not_mutate_the_judge_result():
    state = ConversationState("fixture", now_fn=lambda: 100.0)
    result = {"should_exit": True, "exit_farewell": True, "episode_phase": "exiting"}
    first = enforce_exit_gate(state, {}, result)
    assert not first["should_exit"]
    assert result["should_exit"]
    state.episode_state = state.episode_state.merge(first)
    second = enforce_exit_gate(state, {}, result)
    assert second["exiting_streak"] == 2
    assert second["should_exit"]


def test_directed_message_wins_over_an_exit_and_uses_the_scene_clock():
    state = ConversationState("fixture", now_fn=lambda: 100.0)
    state.episode_state.episode_phase = "exiting"
    state.episode_state.exiting_streak = 2
    decision = enforce_exit_gate(state, {"_reply_to_bot": True}, {"should_exit": True})
    assert not decision["should_exit"]
    reset_for_directed_message(state)
    assert state.episode_state.episode_phase == "mid"
    assert state.episode_state.exiting_streak == 0
    assert state.episode_state.updated_at == 100.0


def test_empty_episode_reopens_as_starting():
    state = ConversationState("fixture", now_fn=lambda: 100.0)
    reset_for_directed_message(state)
    assert state.episode_state.episode_phase == "starting"
