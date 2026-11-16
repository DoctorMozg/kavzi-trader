import builtins
import fnmatch


class _FakePipeline:
    """Queues sync-looking calls and replays them on execute, like redis-py."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str) -> object:
        def queue(*args: object, **kwargs: object) -> _FakePipeline:
            self._ops.append((name, args, kwargs))
            return self

        return queue

    async def execute(self) -> list[object]:
        return [await getattr(self._redis, n)(*a, **k) for n, a, k in self._ops]


class FakeRedis:
    """In-memory subset of redis.asyncio used by state stores and the queue."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, builtins.set[str]] = {}
        self.strings: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

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
        timeout: int,  # noqa: ASYNC109 - mirrors redis-py blmove signature
        src: str = "LEFT",
        dest: str = "RIGHT",
    ) -> str | None:
        return await self.lmove(first_list, second_list, src, dest)

    async def lrem(self, key: str, count: int, value: str) -> int:
        items = self.lists.get(key, [])
        if value in items:
            items.remove(value)
            return 1
        return 0
