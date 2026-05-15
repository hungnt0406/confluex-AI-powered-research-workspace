"""Service layer for the document-level writer chat."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.writer_chat import (
    ChatMessage as AgentChatMessage,
)
from backend.agents.writer_chat import (
    SectionContent,
    SectionPatch,
    SectionRef,
    WriterChatAgent,
)
from backend.agents.writer_editor import EditPatch, TextSpan, citation_keys
from backend.config import get_settings
from backend.db.models import WriterDocument, WriterSection
from backend.services.chat_session_store import (
    ChatMessageRecord,
    ChatSession,
    ChatSessionMeta,
    ChatSessionStore,
    StoredPatch,
    StoredTextSpan,
    get_chat_session_store,
)
from backend.services.writer_documents import WriterDocumentService
from backend.services.writer_editor import WriterEditConflictError, WriterEditorService


class ChatNotFoundError(LookupError):
    """Raised when a chat id is not present (or expired) in the session store."""


class ChatPatchNotFoundError(LookupError):
    """Raised when a referenced patch index/message is missing."""


class ChatPatchStateError(RuntimeError):
    """Raised when a patch state transition is invalid (e.g., accept after reject)."""


class WriterChatService:
    """Wire the writer chat agent + session store + DB editor service together."""

    def __init__(
        self,
        *,
        agent: WriterChatAgent | None = None,
        session_store: ChatSessionStore | None = None,
        writer_document_service: WriterDocumentService | None = None,
        writer_editor_service: WriterEditorService | None = None,
    ) -> None:
        self.agent = agent or WriterChatAgent()
        self._session_store = session_store
        self.writer_document_service = writer_document_service or WriterDocumentService()
        self.writer_editor_service = writer_editor_service or WriterEditorService(
            writer_document_service=self.writer_document_service,
        )

    async def _store(self) -> ChatSessionStore:
        if self._session_store is None:
            self._session_store = await get_chat_session_store()
        return self._session_store

    @property
    def _ttl(self) -> int:
        return get_settings().writer_chat_session_ttl_seconds

    # ------------------------------------------------------------------ create / list / get

    async def create_chat(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> ChatSession:
        await self._ensure_document(session=session, document_id=document_id, user_id=user_id)
        chat_id = str(uuid.uuid4())
        now = time.time()
        chat = ChatSession(
            id=chat_id,
            document_id=document_id,
            user_id=user_id,
            messages=[],
            last_active_at=now,
            history_summary="",
        )
        store = await self._store()
        await store.put(chat_id, chat, self._ttl)
        return chat

    async def list_chats(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> list[ChatSessionMeta]:
        await self._ensure_document(session=session, document_id=document_id, user_id=user_id)
        store = await self._store()
        return await store.list_for_document(document_id, user_id)

    async def get_chat(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        chat_id: str,
    ) -> ChatSession:
        await self._ensure_document(session=session, document_id=document_id, user_id=user_id)
        chat = await self._fetch_chat(
            chat_id=chat_id, document_id=document_id, user_id=user_id
        )
        store = await self._store()
        await store.touch(chat_id, self._ttl)
        return chat

    # ------------------------------------------------------------------ post message

    async def post_message(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        chat_id: str,
        user_message: str,
    ) -> ChatSession:
        doc = await self._ensure_document(
            session=session, document_id=document_id, user_id=user_id
        )
        chat = await self._fetch_chat(
            chat_id=chat_id, document_id=document_id, user_id=user_id
        )
        sections = sorted(doc.sections, key=lambda s: s.order_index)
        outline = [
            SectionRef(
                id=sec.id,
                title=sec.title,
                length=len(sec.draft_latex or ""),
                position=sec.order_index,
            )
            for sec in sections
        ]
        included_sections = self._pick_sections(sections=sections, user_message=user_message)
        known_keys = self._known_citation_keys(doc=doc, sections=sections)
        recent_history, dropped = self._slice_history(chat.messages)
        agent_history = [
            AgentChatMessage(role=m.role, content=m.content) for m in recent_history
        ]
        dropped_summary = self._fold_history_summary(chat.history_summary, dropped)

        response = await self.agent.respond(
            document_outline=outline,
            included_sections=included_sections,
            known_citation_keys=known_keys,
            chat_history=agent_history,
            user_message=user_message,
            history_summary=dropped_summary,
            max_tokens=get_settings().writer_chat_max_tokens,
        )

        verified_patches, stale_notes = self._verify_against_current_draft(
            response.patches, sections
        )
        reply = response.reply
        if stale_notes:
            reply = (reply + " " + " ".join(stale_notes)).strip()

        now = time.time()
        user_record = ChatMessageRecord(
            id=str(uuid.uuid4()),
            role="user",
            content=user_message,
            patches=[],
            created_at=now,
        )
        assistant_record = ChatMessageRecord(
            id=str(uuid.uuid4()),
            role="assistant",
            content=reply,
            patches=[
                StoredPatch(
                    section_id=p.section_id,
                    section_title=p.section_title,
                    span=StoredTextSpan(start=p.span.start, end=p.span.end),
                    original_text=p.original_text,
                    new_text=p.new_text,
                    rationale=p.rationale,
                    status="pending",
                )
                for p in verified_patches
            ],
            created_at=now + 0.0001,
        )
        new_messages = [*chat.messages, user_record, assistant_record]
        updated = replace(
            chat,
            messages=new_messages,
            last_active_at=now,
            history_summary=dropped_summary,
        )
        store = await self._store()
        await store.put(chat.id, updated, self._ttl)
        return updated

    # ------------------------------------------------------------------ patch actions

    async def accept_patch(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        chat_id: str,
        message_id: str,
        patch_index: int,
    ) -> WriterSection:
        chat = await self._fetch_chat(
            chat_id=chat_id, document_id=document_id, user_id=user_id
        )
        message, patch = self._locate_patch(chat, message_id, patch_index)
        if patch.status != "pending":
            raise ChatPatchStateError(f"Patch is already {patch.status}.")

        edit_patch = EditPatch(
            span=TextSpan(start=patch.span.start, end=patch.span.end),
            new_text=patch.new_text,
            rationale=patch.rationale,
            original_text=patch.original_text,
        )
        try:
            section = await self.writer_editor_service.apply(
                session=session,
                document_id=document_id,
                section_id=patch.section_id,
                user_id=user_id,
                patch=edit_patch,
            )
        except WriterEditConflictError:
            await self._update_patch_status(chat, message_id, patch_index, "stale")
            raise
        await self._update_patch_status(chat, message_id, patch_index, "applied")
        return section

    async def reject_patch(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        chat_id: str,
        message_id: str,
        patch_index: int,
    ) -> None:
        await self._ensure_document(session=session, document_id=document_id, user_id=user_id)
        chat = await self._fetch_chat(
            chat_id=chat_id, document_id=document_id, user_id=user_id
        )
        _, patch = self._locate_patch(chat, message_id, patch_index)
        if patch.status != "pending":
            raise ChatPatchStateError(f"Patch is already {patch.status}.")
        await self._update_patch_status(chat, message_id, patch_index, "rejected")

    async def undo_patch(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        chat_id: str,
        message_id: str,
        patch_index: int,
    ) -> WriterSection:
        await self._ensure_document(session=session, document_id=document_id, user_id=user_id)
        chat = await self._fetch_chat(
            chat_id=chat_id, document_id=document_id, user_id=user_id
        )
        _, patch = self._locate_patch(chat, message_id, patch_index)
        if patch.status != "applied":
            raise ChatPatchStateError("Only applied patches can be undone.")

        versions = await self.writer_document_service.get_section_versions(
            session=session,
            section_id=patch.section_id,
            user_id=user_id,
        )
        if not versions:
            raise ChatPatchStateError("No prior version available to restore.")
        latest = versions[0]
        section = await self.writer_document_service.revert_to_version(
            session=session,
            section_id=patch.section_id,
            version_id=latest.id,
            user_id=user_id,
        )
        # After undo the section content is restored to the pre-apply state,
        # so the patch's original_text still matches the current draft span.
        # Reset the status to "pending" so the user can accept (or reject) it
        # again without having to ask the assistant for a fresh proposal.
        await self._update_patch_status(chat, message_id, patch_index, "pending")
        return section

    # ------------------------------------------------------------------ helpers

    async def _ensure_document(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> WriterDocument:
        return await self.writer_document_service.get_document(
            session=session, document_id=document_id, user_id=user_id
        )

    async def _fetch_chat(
        self, *, chat_id: str, document_id: str, user_id: str
    ) -> ChatSession:
        store = await self._store()
        chat = await store.get(chat_id)
        if (
            chat is None
            or chat.document_id != document_id
            or chat.user_id != user_id
        ):
            raise ChatNotFoundError(f"Chat '{chat_id}' not found.")
        return chat

    def _pick_sections(
        self,
        *,
        sections: list[WriterSection],
        user_message: str,
    ) -> list[SectionContent]:
        cap = get_settings().writer_chat_max_included_sections
        if cap <= 0:
            return []
        lower_msg = user_message.lower()
        mentioned: list[WriterSection] = []
        for sec in sections:
            title = (sec.title or "").strip()
            if title and title.lower() in lower_msg:
                mentioned.append(sec)
        recent = sorted(
            sections,
            key=lambda s: s.updated_at,
            reverse=True,
        )[:3]
        ordered: list[WriterSection] = []
        seen: set[str] = set()
        for sec in mentioned + recent:
            if sec.id in seen:
                continue
            ordered.append(sec)
            seen.add(sec.id)
            if len(ordered) >= cap:
                break
        return [
            SectionContent(id=sec.id, title=sec.title, draft_latex=sec.draft_latex or "")
            for sec in ordered
        ]

    def _known_citation_keys(
        self,
        *,
        doc: WriterDocument,
        sections: list[WriterSection],
    ) -> set[str]:
        keys: set[str] = set(doc.source_paper_ids_json or [])
        for source in doc.sources:
            if source.paper_id:
                keys.add(source.paper_id)
        for sec in sections:
            keys.update(citation_keys(sec.draft_latex or ""))
        return keys

    def _slice_history(
        self, messages: list[ChatMessageRecord]
    ) -> tuple[list[ChatMessageRecord], list[ChatMessageRecord]]:
        window = max(1, get_settings().writer_chat_context_window_turns)
        # Each "turn" = user + assistant pair (~2 messages). Use direct message count cap.
        max_messages = window * 2
        if len(messages) <= max_messages:
            return list(messages), []
        return messages[-max_messages:], messages[:-max_messages]

    def _fold_history_summary(
        self,
        existing_summary: str,
        dropped: list[ChatMessageRecord],
    ) -> str:
        if not dropped:
            return existing_summary
        snippets = [existing_summary] if existing_summary else []
        for msg in dropped:
            if msg.role != "assistant":
                continue
            text = (msg.content or "").strip()
            if text:
                snippets.append(text[:140])
        return " | ".join(snippets)[:2_000]

    def _verify_against_current_draft(
        self,
        patches: list[SectionPatch],
        sections: list[WriterSection],
    ) -> tuple[list[SectionPatch], list[str]]:
        by_id = {sec.id: sec for sec in sections}
        verified: list[SectionPatch] = []
        warnings: list[str] = []
        for patch in patches:
            section = by_id.get(patch.section_id)
            if section is None:
                warnings.append(
                    f"Dropped patch for {patch.section_title!r}: section is missing."
                )
                continue
            draft = section.draft_latex or ""
            if (
                patch.span.start < 0
                or patch.span.end < patch.span.start
                or patch.span.end > len(draft)
            ):
                warnings.append(
                    f"Dropped patch in {patch.section_title!r}: span no longer valid."
                )
                continue
            if draft[patch.span.start : patch.span.end] != patch.original_text:
                warnings.append(
                    f"Dropped patch in {patch.section_title!r}: draft changed since the proposal."
                )
                continue
            verified.append(patch)
        return verified, warnings

    def _locate_patch(
        self,
        chat: ChatSession,
        message_id: str,
        patch_index: int,
    ) -> tuple[ChatMessageRecord, StoredPatch]:
        for message in chat.messages:
            if message.id != message_id:
                continue
            if patch_index < 0 or patch_index >= len(message.patches):
                raise ChatPatchNotFoundError(
                    f"Patch index {patch_index} out of range for message {message_id}."
                )
            return message, message.patches[patch_index]
        raise ChatPatchNotFoundError(f"Message '{message_id}' not found.")

    async def _update_patch_status(
        self,
        chat: ChatSession,
        message_id: str,
        patch_index: int,
        new_status: str,
    ) -> ChatSession:
        new_messages: list[ChatMessageRecord] = []
        for message in chat.messages:
            if message.id != message_id:
                new_messages.append(message)
                continue
            updated_patches = list(message.patches)
            patch = updated_patches[patch_index]
            updated_patches[patch_index] = replace(patch, status=new_status)
            new_messages.append(replace(message, patches=updated_patches))
        updated = replace(chat, messages=new_messages, last_active_at=time.time())
        store = await self._store()
        await store.put(chat.id, updated, self._ttl)
        return updated


__all__ = [
    "ChatNotFoundError",
    "ChatPatchNotFoundError",
    "ChatPatchStateError",
    "WriterChatService",
]
