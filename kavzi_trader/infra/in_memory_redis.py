from __future__ import annotations

import builtins
import fnmatch


class _InMemoryPipeline:
    """Queues sync-looking calls and replays them on execute, like redis-py."""

    def __init__(self, redis: InMemoryRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str) -> object:
        def queue(*args: object, **kwargs: object) -> _InMemoryPipeline:
            self._ops.append((name, args, kwargs))
            return self

        return queue

    async def execute(self) -> list[object]:
        return [await getattr(self._redis, n)(*a, **k) for n, a, k in self._ops]


class InMemoryRedis:
    """In-memory subset of redis.asyncio for replays and tests; one process only."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, builtins.set[str]] = {}
        self.strings: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._stream_seq = 0

    def pipeline(self) -> _InMemoryPipeline:
        return _InMemoryPipeline(self)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key: str, *fields: str) -> int:
        stored = self.hashes.get(key, {})
        return sum(stored.pop(field, None) is not None for field in fields)

    async def keys(self, pattern: str) -> list[str]:
        names = [*self.hashes, *self.strings]
        return [name for name in names if fnmatch.fnmatch(name, pattern)]

    async def delete(self, key: str) -> int:
        found = key in self.hashes or key in self.strings or key in self.sets
        self.hashes.pop(key, None)
        self.strings.pop(key, None)
        self.sets.pop(key, None)
        return int(found)

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def set(self, key: str, value: str) -> None:
        self.strings[key] = value

    async def sadd(self, key: str, *members: str) -> int:
        self.sets.setdefault(key, builtins.set()).update(members)
        return len(members)

    async def srem(self, key: str, *members: str) -> int:
        self.sets.get(key, builtins.set()).difference_update(members)
        return len(members)

    async def smembers(self, key: str) -> builtins.set[str]:
        return builtins.set(self.sets.get(key, builtins.set()))

    async def scard(self, key: str) -> int:
        return len(self.sets.get(key, builtins.set()))

    async def lpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).insert(0, value)

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def lmove(
        self,
        first_list: str,
        second_list: str,
        src: str = "LEFT",
        dest: str = "RIGHT",
    ) -> str | None:
        source = self.lists.get(first_list, [])
        if not source:
            return None
        value = source.pop(0 if src == "LEFT" else -1)
        target = self.lists.setdefault(second_list, [])
        target.insert(0, value) if dest == "LEFT" else target.append(value)
        return value

    async def blmove(
        self,
        first_list: str,
        second_list: str,
        timeout: int,  # noqa: ARG002, ASYNC109 - mirrors redis-py blmove signature
        src: str = "LEFT",
        dest: str = "RIGHT",
    ) -> str | None:
        return await self.lmove(first_list, second_list, src, dest)

    async def lrem(self, key: str, count: int, value: str) -> int:
        # Redis semantics: count > 0 from the head, < 0 from the tail, 0 removes all.
        items = self.lists.get(key, [])
        limit = abs(count) or len(items)
        order = range(len(items) - 1, -1, -1) if count < 0 else range(len(items))
        hits = [i for i in order if items[i] == value][:limit]
        for i in sorted(hits, reverse=True):
            del items[i]
        return len(hits)

    async def xadd(
        self,
        name: str,
        fields: dict[str, str],
        maxlen: int | None = None,
        approximate: bool = True,  # noqa: ARG002 - mirrors redis-py xadd signature
    ) -> str:
        stream = self.streams.setdefault(name, [])
        self._stream_seq += 1
        entry_id = f"{self._stream_seq}-0"
        stream.append((entry_id, dict(fields)))
        if maxlen is not None and len(stream) > maxlen:
            del stream[: len(stream) - maxlen]
        return entry_id

    async def xrange(
        self,
        name: str,
        min: str = "-",  # noqa: A002 - mirrors redis-py xrange signature
        max: str = "+",  # noqa: A002 - mirrors redis-py xrange signature
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        if (min, max) != ("-", "+"):
            msg = f"InMemoryRedis.xrange supports only - and +, got {min}..{max}"
            raise ValueError(msg)
        entries = list(self.streams.get(name, []))
        return entries if count is None else entries[:count]
