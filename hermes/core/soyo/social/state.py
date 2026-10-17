# SPDX-License-Identifier: MIT
"""Platform-neutral state retained from the QQ customizations; no legacy engine.

This module contains data/policy only. It cannot call a model, start a gateway,
or send a message. Native DSH remains the sole execution path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import time


@dataclass
class ConversationMessage:
    message_id: str = ""
    text: str = ""
    seq: int = 0
    timestamp: float = 0.0
    sender_id: str = ""
    name: str = ""
    is_bot: bool = False
    media_paths: list[str] = field(default_factory=list)


@dataclass
class AttentionState:
    active: bool = False
    silent_count: int = 0
    last_active_ts: float = 0.0
    last_reply: str = ""


@dataclass
class EpisodeState:
    status: str = "active"
    continuity: str = "same_episode"
    turn_count: int = 0
    exiting_streak: int = 0
    episode_label: str = ""
    current_thread: str = ""
    conversation_mode: str = ""
    episode_phase: str = "empty"
    last_speaker_role: str = ""
    bot_moves: list[str] = field(default_factory=list)
    overused_moves: list[str] = field(default_factory=list)
    open_loops: list[str] = field(default_factory=list)
    resolved_threads: list[str] = field(default_factory=list)
    progression_guidance: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        for old, new in (("episode_status", "status"), ("soyo_moves", "bot_moves"), ("speaker_role", "last_speaker_role")):
            if old in value and new not in value: value[new] = value[old]
        try: value['exiting_streak'] = max(0, min(2, int(value.get('exiting_streak', 0) or 0)))
        except (ValueError, TypeError, OverflowError): value['exiting_streak'] = 0
        return cls(**{item.name: value[item.name] for item in fields(cls) if item.name in value})

    def merge(self, value):
        return self.from_dict({**self.to_dict(), **dict(value)})


class ConversationState:
    def __init__(self, scene_id, *, now_fn=time.time):
        self.scene_id, self._now = scene_id, now_fn
        self.buffer, self.by_id = [], {}
        self.next_seq = self.last_user_seq = self.quiet_since_seq = 0
        self.decision_epoch = self.state_revision = self.reply_count = 0
        self.last_reply = None
        self.attentive, self.episode_state = AttentionState(), EpisodeState()

    def append_message(self, message):
        self.next_seq += 1
        message.seq = self.next_seq
        self.buffer.append(message)
        if not message.is_bot: self.last_user_seq = message.seq
        if message.message_id: self.by_id[message.message_id] = message
        if len(self.buffer) > 250:
            self.buffer = self.buffer[-200:]
            self.by_id = {item.message_id: item for item in self.buffer if item.message_id}
        self.state_revision += 1
        return message

    def snapshot(self, up_to_seq=None):
        ceiling = self.last_user_seq if up_to_seq is None else up_to_seq
        return tuple(item for item in self.buffer if item.seq <= ceiling)

    def lookup_message(self, message_id):
        return self.by_id.get(message_id)

    def latest_user_message(self):
        return next((item for item in reversed(self.buffer) if not item.is_bot), None)

    def record_reply(self, text=""):
        self.attentive = AttentionState(True, 0, self._now(), text)
        self.last_reply = (self._now(), text)
        self.reply_count += 1
        self.state_revision += 1

    def go_quiet(self):
        if self.attentive.active or self.last_reply is not None:
            self.decision_epoch += 1
            self.quiet_since_seq = self.last_user_seq
            self.state_revision += 1
        self.attentive.active = False
        self.last_reply = None

    def record_silent(self):
        if self.attentive.active:
            self.attentive.silent_count += 1
            if self.attentive.silent_count >= 3: self.go_quiet()

    def is_attentive(self):
        if self.attentive.active and self._now() - self.attentive.last_active_ts > 600: self.go_quiet()
        return self.attentive.active

    def is_episode_active(self):
        return self.last_reply is not None
