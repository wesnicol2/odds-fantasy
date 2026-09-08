from itertools import pairwise

from oddsfantasy.graph_data import distribution_graph
from oddsfantasy.market_math import Anchor, ContinuousDistribution, CountDistribution


class UniformHundredDistribution:
    def quantile(self, u: float) -> float:
        return 100.0 * u

    def sf(self, x: float) -> float:
        return 1.0 - max(0.0, min(1.0, x / 100.0))


def test_low_granularity_count_graph_uses_threshold_probabilities():
    graph = distribution_graph(CountDistribution({0: 0.2, 1: 0.5, 2: 0.3}), "player_pass_tds")

    assert graph["kind"] == "threshold_gauge"
    assert graph["points"] == [
        {"x": 1.0, "probability": 0.8},
        {"x": 2.0, "probability": 0.3},
    ]


def test_high_granularity_count_graph_uses_exact_probability_mass():
    graph = distribution_graph(
        CountDistribution({0: 0.2, 1: 0.5, 2: 0.3}),
        "player_receptions",
    )

    assert graph["kind"] == "discrete_pmf"
    assert graph["points"] == [
        {"x": 0.0, "probability": 0.2},
        {"x": 1.0, "probability": 0.5},
        {"x": 2.0, "probability": 0.3},
    ]


def test_yardage_graph_is_probability_density_over_focused_range():
    graph = distribution_graph(UniformHundredDistribution(), "player_rush_yds")

    assert graph["kind"] == "continuous_density"
    assert len(graph["points"]) == 181
    assert graph["points"][0]["x"] == 0.5
    assert graph["points"][-1]["x"] == 95.0
    midpoint = min(graph["points"], key=lambda point: abs(point["x"] - 50.0))
    assert abs(midpoint["probability"] - 0.01) < 0.001
    assert all(point["probability"] >= 0 for point in graph["points"])


def test_continuous_density_smooths_sparse_anchor_gaps():
    distribution = ContinuousDistribution(
        [
            Anchor(10.0, 0.90),
            Anchor(20.0, 0.76),
            Anchor(30.0, 0.76),
            Anchor(40.0, 0.56),
            Anchor(50.0, 0.56),
            Anchor(60.0, 0.34),
            Anchor(70.0, 0.34),
            Anchor(85.0, 0.10),
        ]
    )

    graph = distribution_graph(distribution, "player_rush_yds")
    interior = [
        point["probability"]
        for point in graph["points"]
        if 15.0 <= point["x"] <= 75.0
    ]

    assert graph["kind"] == "continuous_density"
    assert len(graph["points"]) == 181
    assert interior
    assert min(interior) > 0.0
    peak = max(interior)
    assert max(abs(right - left) for left, right in pairwise(interior)) < peak * 0.2
