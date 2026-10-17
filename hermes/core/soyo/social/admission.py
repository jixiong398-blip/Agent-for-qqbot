"""Platform-neutral admission rules extracted from the QQ trigger path."""

from __future__ import annotations

from typing import Any, Mapping

from .state import ConversationState


def reset_for_directed_message(state: ConversationState) -> None:
    """Re-open an episode before a directed @/reply is admitted."""

    episode = state.episode_state
    old_phase = episode.episode_phase or "empty"
    episode.exiting_streak = 0
    if old_phase == "exiting":
        episode.episode_phase = "mid"
    elif old_phase in ("winding_down", "empty"):
        episode.episode_phase = "starting"
    episode.progression_guidance = ""
    if old_phase in ("exiting", "winding_down", "empty"):
        episode.episode_label = ""
        episode.conversation_mode = ""
    episode.updated_at = state._now()
    episode.status = "active"
    state.state_revision += 1


def enforce_exit_gate(
    state: ConversationState | None,
    message_flags: Mapping[str, Any],
    result: Mapping[str, Any] | Any,
) -> Any:
    """Require two consecutive exit observations unless the message is directed.

    This is intentionally a pure policy boundary: a caller still decides how
    to persist the returned decision or submit a turn to DSH.
    """

    if not isinstance(result, Mapping):
        return result
    decision = dict(result)
    episode = getattr(state, "episode_state", None)
    prior_phase = str(getattr(episode, "episode_phase", "") or "")
    try:
        prior_streak = max(0, min(2, int(getattr(episode, "exiting_streak", 0) or 0)))
    except (TypeError, ValueError, OverflowError):
        prior_streak = 0

    directed = bool(message_flags.get("_is_mentioned") or message_flags.get("_reply_to_bot"))
    candidate_phase = str(decision.get("episode_phase", "") or "")
    if directed:
        decision.update({
            "should_exit": False,
            "exit_farewell": False,
            "episode_phase": "mid",
            "exiting_streak": 0,
        })
        return decision

    wants_exit = bool(decision.get("should_exit")) or candidate_phase == "exiting"
    if prior_phase == "exiting" and candidate_phase not in ("mid", "starting", "winding_down"):
        wants_exit = True
        candidate_phase = "exiting"
    if not wants_exit:
        decision["exiting_streak"] = 0
        return decision

    candidate_phase = "exiting"
    streak = min(2, prior_streak + 1 if prior_phase == "exiting" else 1)
    decision["episode_phase"] = candidate_phase
    decision["exiting_streak"] = streak
    if streak < 2:
        decision["should_exit"] = False
        decision["exit_farewell"] = False
    return decision
