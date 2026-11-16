import pytest

from kavzi_trader.infra.in_memory_redis import InMemoryRedis


@pytest.mark.parametrize(
    ("count", "left"),
    [(1, ["b", "a", "a"]), (-1, ["a", "b", "a"]), (0, ["b"])],
)
async def test_lrem_follows_redis_count_semantics(count: int, left: list[str]) -> None:
    redis = InMemoryRedis()
    redis.lists["q"] = ["a", "b", "a", "a"]

    removed = await redis.lrem("q", count, "a")

    assert redis.lists["q"] == left
    assert removed == 4 - len(left)


async def test_xadd_trims_to_maxlen_and_keeps_ids_unique() -> None:
    redis = InMemoryRedis()
    ids = [await redis.xadd("s", {"n": str(n)}, maxlen=2) for n in range(3)]

    entries = await redis.xrange("s")

    assert len(set(ids)) == 3
    assert [fields["n"] for _, fields in entries] == ["1", "2"]
