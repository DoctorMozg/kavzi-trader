from kavzi_trader.brain.agent.circuit_breaker import AgentCircuitBreaker


class TestCooldown:
    def test_no_cooldown_by_default(self) -> None:
        breaker = AgentCircuitBreaker(threshold=1)
        breaker.record_failure("BTCUSDT")
        assert breaker.is_open("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 0
        assert breaker.is_open("BTCUSDT")

    def test_cooldown_not_armed_below_threshold(self) -> None:
        breaker = AgentCircuitBreaker(threshold=2, cooldown_cycles=2)
        breaker.record_failure("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 0

    def test_cycles_count_down_and_reset_on_last(self) -> None:
        breaker = AgentCircuitBreaker(threshold=2, cooldown_cycles=2)
        breaker.record_failure("BTCUSDT")
        breaker.record_failure("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 2
        assert breaker.is_open("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 1
        assert not breaker.is_open("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 0

    def test_reset_clears_cooldown(self) -> None:
        breaker = AgentCircuitBreaker(threshold=1, cooldown_cycles=3)
        breaker.record_failure("BTCUSDT")
        breaker.reset("BTCUSDT")
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 0

    def test_cooldown_is_per_symbol(self) -> None:
        breaker = AgentCircuitBreaker(threshold=1, cooldown_cycles=2)
        breaker.record_failure("BTCUSDT")
        assert breaker.consume_cooldown_cycle("ETHUSDT") == 0
        assert breaker.consume_cooldown_cycle("BTCUSDT") == 2
