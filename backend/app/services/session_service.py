"""Redis-backed chat session metadata and ownership operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from redis.exceptions import RedisError

from app.core.config import settings
from app.db.redis import (
    RedisUnavailableError,
    get_redis_checkpointer,
    get_redis_client,
)


class SessionNotFoundError(LookupError):
    """Raised for missing sessions and ownership mismatches alike."""


def _metadata_key(user_id: int, thread_id: str) -> str:
    return f"{settings.redis_key_prefix}:session:{user_id}:{thread_id}"


def _index_key(user_id: int) -> str:
    return f"{settings.redis_key_prefix}:user_sessions:{user_id}"


def _decode_metadata(raw: dict[bytes, bytes]) -> dict[str, str]:
    return {key.decode(): value.decode() for key, value in raw.items()}


def _execute(operation):
    try:
        return operation()
    except RedisError as exc:
        raise RedisUnavailableError("Redis 会话服务当前不可用。") from exc


def create_session(user_id: int) -> dict[str, str]:
    thread_id = str(uuid4())
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    metadata = {
        "thread_id": thread_id,
        "user_id": str(user_id),
        "title": "新会话",
        "created_at": now_iso,
        "updated_at": now_iso,
        "last_message_preview": "",
    }

    def operation():
        client = get_redis_client()
        with client.pipeline(transaction=True) as pipe:
            pipe.hset(_metadata_key(user_id, thread_id), mapping=metadata)
            if settings.session_ttl_seconds > 0:
                pipe.expire(
                    _metadata_key(user_id, thread_id), settings.session_ttl_seconds
                )
            pipe.zadd(_index_key(user_id), {thread_id: now.timestamp()})
            if settings.session_ttl_seconds > 0:
                pipe.expire(_index_key(user_id), settings.session_ttl_seconds)
            pipe.execute()

    _execute(operation)
    return metadata


def get_session(user_id: int, thread_id: UUID | str) -> dict[str, str]:
    normalized = str(thread_id)
    raw = _execute(
        lambda: get_redis_client().hgetall(_metadata_key(user_id, normalized))
    )
    if not raw:
        raise SessionNotFoundError("会话不存在。")
    metadata = _decode_metadata(raw)
    if metadata.get("user_id") != str(user_id):
        raise SessionNotFoundError("会话不存在。")
    return metadata


def validate_session_owner(user_id: int, thread_id: UUID | str) -> dict[str, str]:
    return get_session(user_id, thread_id)


def get_session_messages(
    user_id: int, thread_id: UUID | str
) -> list[dict[str, str]]:
    """Read the public human/AI message history from the latest checkpoint."""
    validate_session_owner(user_id, thread_id)
    normalized = str(thread_id)
    checkpoint = get_redis_checkpointer().get_tuple(
        {"configurable": {"thread_id": normalized}}
    )
    if checkpoint is None:
        return []

    result: list[dict[str, str]] = []
    state = checkpoint.checkpoint.get("channel_values", {})
    for message in state.get("messages", []):
        if not isinstance(message.content, str):
            continue
        if isinstance(message, HumanMessage):
            result.append({"role": "user", "content": message.content})
        elif isinstance(message, AIMessage):
            result.append({"role": "assistant", "content": message.content})
    return result


def list_sessions(user_id: int) -> list[dict[str, str]]:
    def operation():
        client = get_redis_client()
        thread_ids = client.zrevrange(_index_key(user_id), 0, -1)
        result = []
        stale = []
        for raw_thread_id in thread_ids:
            thread_id = raw_thread_id.decode()
            raw = client.hgetall(_metadata_key(user_id, thread_id))
            if raw:
                result.append(_decode_metadata(raw))
            else:
                stale.append(thread_id)
        if stale:
            client.zrem(_index_key(user_id), *stale)
        return result

    return _execute(operation)


def _title_for_message(message: str) -> str:
    if any(word in message for word in ("查询", "查看", "记录", "待审批")):
        return "请假查询"
    if any(word in message for word in ("请假", "年假", "事假", "病假")):
        return "请假申请"
    if any(word in message for word in ("批准", "拒绝", "审批")):
        return "请假审批"
    return "OA 助手会话"


def touch_session(user_id: int, thread_id: UUID | str, message: str) -> dict[str, str]:
    metadata = get_session(user_id, thread_id)
    normalized = str(thread_id)
    now = datetime.now(UTC)
    updates = {
        "updated_at": now.isoformat(),
        "last_message_preview": message[:100],
    }
    if metadata.get("title") == "新会话":
        updates["title"] = _title_for_message(message)

    def operation():
        client = get_redis_client()
        with client.pipeline(transaction=True) as pipe:
            pipe.hset(_metadata_key(user_id, normalized), mapping=updates)
            if settings.session_ttl_seconds > 0:
                pipe.expire(
                    _metadata_key(user_id, normalized),
                    settings.session_ttl_seconds,
                )
            pipe.zadd(_index_key(user_id), {normalized: now.timestamp()})
            if settings.session_ttl_seconds > 0:
                pipe.expire(_index_key(user_id), settings.session_ttl_seconds)
            pipe.execute()

    _execute(operation)
    return {**metadata, **updates}


def delete_session(user_id: int, thread_id: UUID | str) -> None:
    validate_session_owner(user_id, thread_id)
    normalized = str(thread_id)
    get_redis_checkpointer().delete_thread(normalized)

    def operation():
        client = get_redis_client()
        with client.pipeline(transaction=True) as pipe:
            pipe.delete(_metadata_key(user_id, normalized))
            pipe.zrem(_index_key(user_id), normalized)
            pipe.execute()

    _execute(operation)
