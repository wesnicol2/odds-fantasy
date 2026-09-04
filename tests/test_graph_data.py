from itertools import pairwise

from oddsfantasy.graph_data import distribution_graph
from oddsfantasy.market_math import CountDistribution


class UniformHundredDistribution:
    def quantile(self, u: float) -> float:
        return 100.0 * u

    def sf(self, x: float) -> float:
        return 1.0 - max(0.0, min(1.0, x / 100.0))


def test_count_graph_uses_cumulative_probability_curve():
    graph = distribution_graph(CountDistribution({0: 0.2, 1: 0.5, 2: 0.3}), "player_pass_tds")

    assert graph["kind"] == "survival_step"
    assert graph["points"] == [
        {"x": 1.0, "probability": 0.8},
        {"x": 2.0, "probability": 0.3},
    ]


def test_yardage_graph_is_smooth_fitted_survival_curve():
    graph = distribution_graph(UniformHundredDistribution(), "player_rush_yds")

    assert graph["kind"] == "survival"
    assert len(graph["points"]) == 101
    probabilities = [point["probability"] for point in graph["points"]]
    assert all(left >= right for left, right in pairwise(probabilities))
    midpoint = min(graph["points"], key=lambda point: abs(point["x"] - 50.0))
    assert abs(midpoint["probability"] - 0.5) < 0.02
