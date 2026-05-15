"""Storage for writer chat sessions (in-memory + optional Redis)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Protocol

from backend.config import get_settings
from backend.services.redis_client import get_redis

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredTextSpan:
    start: int
    end: int


@dataclass(frozen=True)
class StoredPatch:
    section_id: str
    section_title: str
    span: StoredTextSpan
    original_text: str
    new_text: str
    rationale: str
    status: str = "pending"  # "pending" | "applied" | "rejected" | "stale"


@dataclass(frozen=True)
class ChatMessageRecord:
    id: str
    role: str  # "user" | "assistant"
    content: str
    patches: list[StoredPatch] = field(default_factory=list)
    created_at: float = 0.0  # epoch seconds


@dataclass(frozen=True)
class ChatSession:
    id: str
    document_id: str
    user_id: str
    messages: list[ChatMessageRecord] = field(default_factory=list)
    last_active_at: float = 0.0
    history_summary: str = ""


@dataclass(frozen=True)
class ChatSessionMeta:
    id: str
    document_id: str
    user_id: str
    last_active_at: float
    message_count: int


class ChatSessionStore(Protocol):
    async def get(self, chat_id: str) -> ChatSession | None: ...

    async def put(self, chat_id: str, session: ChatSession, ttl_seconds: int) -> None: ...

    async def list_for_document(
        self, document_id: str, user_id: str
    ) -> list[ChatSessionMeta]: ...

    async def delete(self, chat_id: str) -> None: ...

    async def touch(self, chat_id: str, ttl_seconds: int) -> None: ...


def _patch_to_dict(patch: StoredPatch) -> dict[str, Any]:
    data = asdict(patch)
    data["span"] = {"start": patch.span.start, "end": patch.span.end}
    return data


def _patch_from_dict(data: dict[str, Any]) -> StoredPatch:
    span_data = data.get("span") or {}
    return StoredPatch(
        section_id=str(data.get("section_id", "")),
        section_title=str(data.get("section_title", "")),
        span=StoredTextSpan(
            start=int(span_data.get("start", 0)),
            end=int(span_data.get("end", 0)),
        ),
        original_text=str(data.get("original_text", "")),
        new_text=str(data.get("new_text", "")),
        rationale=str(data.get("rationale", "")),
        status=str(data.get("status", "pending")),
    )


def _message_to_dict(message: ChatMessageRecord) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "patches": [_patch_to_dict(p) for p in message.patches],
        "created_at": message.created_at,
    }


def _message_from_dict(data: dict[str, Any]) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=str(data.get("id", "")),
        role=str(data.get("role", "user")),
        content=str(data.get("content", "")),
        patches=[_patch_from_dict(p) for p in (data.get("patches") or [])],
        created_at=float(data.get("created_at", 0.0)),
    )


def _session_to_dict(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "document_id": session.document_id,
        "user_id": session.user_id,
        "messages": [_message_to_dict(m) for m in session.messages],
        "last_active_at": session.last_active_at,
        "history_summary": session.history_summary,
    }


def _session_from_dict(data: dict[str, Any]) -> ChatSession:
    return ChatSession(
        id=str(data.get("id", "")),
        document_id=str(data.get("document_id", "")),
        user_id=str(data.get("user_id", "")),
        messages=[_message_from_dict(m) for m in (data.get("messages") or [])],
        last_active_at=float(data.get("last_active_at", 0.0)),
        history_summary=str(data.get("history_summary", "")),
    )


class InMemoryChatSessionStore:
    """Process-local store with sliding TTL."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, tuple[ChatSession, float]] = {}
        self._clock: Callable[[], float] = time.time

    def _now(self) -> float:
        return float(self._clock())

    def set_clock(self, clock: Callable[[], float]) -> None:
        self._clock = clock

    def _evict_locked(self) -> None:
        now = self._now()
        expired = [cid for cid, (_, expires_at) in self._entries.items() if expires_at <= now]
        for cid in expired:
            self._entries.pop(cid, None)

    async def get(self, chat_id: str) -> ChatSession | None:
        async with self._lock:
            entry = self._entries.get(chat_id)
            if entry is None:
                return None
            session, expires_at = entry
            if expires_at <= self._now():
                self._entries.pop(chat_id, None)
                return None
            return session

    async def put(self, chat_id: str, session: ChatSession, ttl_seconds: int) -> None:
        async with self._lock:
            self._evict_locked()
            expires_at = self._now() + max(ttl_seconds, 1)
            self._entries[chat_id] = (session, expires_at)

    async def list_for_document(
        self, document_id: str, user_id: str
    ) -> list[ChatSessionMeta]:
        async with self._lock:
            self._evict_locked()
            metas: list[ChatSessionMeta] = []
            for session, _expires in self._entries.values():
                if session.document_id == document_id and session.user_id == user_id:
                    metas.append(
                        ChatSessionMeta(
                            id=session.id,
                            document_id=session.document_id,
                            user_id=session.user_id,
                            last_active_at=session.last_active_at,
                            message_count=len(session.messages),
                        )
                    )
            metas.sort(key=lambda m: m.last_active_at, reverse=True)
            return metas

    async def delete(self, chat_id: str) -> None:
        async with self._lock:
            self._entries.pop(chat_id, None)

    async def touch(self, chat_id: str, ttl_seconds: int) -> None:
        async with self._lock:
            entry = self._entries.get(chat_id)
            if entry is None:
                return
            session, _expires = entry
            self._entries[chat_id] = (session, self._now() + max(ttl_seconds, 1))


class RedisChatSessionStore:
    """Redis-backed store. Key format: writer-chat:{chat_id}."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    @staticmethod
    def _key(chat_id: str) -> str:
        return f"writer-chat:{chat_id}"

    @staticmethod
    def _index_key(document_id: str, user_id: str) -> str:
        return f"writer-chat-index:{document_id}:{user_id}"

    async def get(self, chat_id: str) -> ChatSession | None:
        raw = await self._redis.get(self._key(chat_id))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Discarding malformed chat session %s", chat_id)
            await self._redis.delete(self._key(chat_id))
            return None
        return _session_from_dict(data)

    async def put(self, chat_id: str, session: ChatSession, ttl_seconds: int) -> None:
        payload = json.dumps(_session_to_dict(session))
        ttl = max(ttl_seconds, 1)
        await self._redis.set(self._key(chat_id), payload, ex=ttl)
        await self._redis.sadd(self._index_key(session.document_id, session.user_id), chat_id)
        await self._redis.expire(
            self._index_key(session.document_id, session.user_id),
            ttl,
        )

    async def list_for_document(
        self, document_id: str, user_id: str
    ) -> list[ChatSessionMeta]:
        ids = await self._redis.smembers(self._index_key(document_id, user_id))
        metas: list[ChatSessionMeta] = []
        for cid in ids:
            session = await self.get(cid)
            if session is None:
                await self._redis.srem(self._index_key(document_id, user_id), cid)
                continue
            metas.append(
                ChatSessionMeta(
                    id=session.id,
                    document_id=session.document_id,
                    user_id=session.user_id,
                    last_active_at=session.last_active_at,
                    message_count=len(session.messages),
                )
            )
        metas.sort(key=lambda m: m.last_active_at, reverse=True)
        return metas

    async def delete(self, chat_id: str) -> None:
        session = await self.get(chat_id)
        await self._redis.delete(self._key(chat_id))
        if session is not None:
            await self._redis.srem(
                self._index_key(session.document_id, session.user_id),
                chat_id,
            )

    async def touch(self, chat_id: str, ttl_seconds: int) -> None:
        await self._redis.expire(self._key(chat_id), max(ttl_seconds, 1))


_cached_store: ChatSessionStore | None = None


async def get_chat_session_store() -> ChatSessionStore:
    """Return a cached chat session store (Redis when REDIS_URL is set + available)."""

    global _cached_store
    if _cached_store is not None:
        return _cached_store

    settings = get_settings()
    if settings.redis_url:
        client = await get_redis()
        if client is not None:
            _cached_store = RedisChatSessionStore(client)
            return _cached_store

    _cached_store = InMemoryChatSessionStore()
    return _cached_store


def reset_chat_session_store_for_tests() -> None:
    """Clear the cached store; tests use this to swap implementations."""

    global _cached_store
    _cached_store = None


def replace_message(
    session: ChatSession, message_id: str, updated: ChatMessageRecord
) -> ChatSession:
    new_messages = [updated if m.id == message_id else m for m in session.messages]
    return replace(session, messages=new_messages)
