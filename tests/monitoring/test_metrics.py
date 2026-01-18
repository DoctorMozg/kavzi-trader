from kavzi_trader.monitoring.metrics import MetricsRegistry


def test_metrics_registry_snapshot() -> None:
    registry = MetricsRegistry()
    registry.inc_counter("orders")
    registry.set_gauge("positions", 2.0)
    registry.observe("latency_ms", 15.0)

    snapshot = registry.snapshot()

    assert snapshot.counters["orders"] == 1
    assert snapshot.gauges["positions"] == 2.0
    assert snapshot.histograms["latency_ms"] == [15.0]
