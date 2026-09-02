from oddsfantasy.graph_data import distribution_graph
from oddsfantasy.market_math import CountDistribution


class UniformHundredDistribution:
    def quantile(self, u: float) -> float:
        return 100.0 * u

    def cdf(self, x: float) -> float:
        return max(0.0, min(1.0, x / 100.0))


def test_count_graph_uses_exact_probability_mass():
    graph = distribution_graph(CountDistribution({0: 0.2, 1: 0.5, 2: 0.3}), "player_pass_tds")

    assert graph["kind"] == "exact_count"
    assert graph["points"] == [
        {"x": 0.0, "probability": 0.2},
        {"x": 1.0, "probability": 0.5},
        {"x": 2.0, "probability": 0.3},
    ]


def test_yardage_graph_is_display_only_five_yard_probability_buckets():
    graph = distribution_graph(UniformHundredDistribution(), "player_rush_yds")

    assert graph["kind"] == "bucket"
    assert graph["bucket_width"] == 5.0
    point_50 = next(point for point in graph["points"] if point["x"] == 50.0)
    assert point_50["probability"] == 0.05
