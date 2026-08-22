"""Steps 1-4 of docs/fantasy-projection-methodology.md, checked against the doc.

The doc's worked examples (§3 for a continuous stat, §4 for a discrete count)
are quoted in pure numbers, which makes them a real test of the code rather
than a restatement of it. Where a number here comes from the doc, the section
is cited.
"""

import unittest

from oddsfantasy.market_math import (
    Anchor,
    ContinuousDistribution,
    CountDistribution,
    american_to_probability,
    build_distribution,
    collect_anchors,
    decimal_to_probability,
    devig_proportional,
    level_for_threshold,
)


def american_to_decimal(odds: float) -> float:
    """The feed is decimal; the doc quotes American. Convert for the fixtures."""
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / -odds)


def two_way(point: float, over_american: float, under_american: float) -> dict:
    return {
        "over": {"odds": american_to_decimal(over_american), "point": point},
        "under": {"odds": american_to_decimal(under_american), "point": point},
    }


def alt_ladder(rungs: list[tuple[float, float, float | None]]) -> dict:
    over = [{"odds": american_to_decimal(o), "point": p} for p, o, _ in rungs]
    under = [{"odds": american_to_decimal(u), "point": p} for p, _, u in rungs if u is not None]
    return {"alts": {"over": over, "under": under}}


# docs/fantasy-projection-methodology.md §3.1 -- one book, main line + ladder.
DOC_RUSH_YDS_BOOK = {
    "player_rush_yds": two_way(74.5, -115, -105),
    "player_rush_yds_alternate": alt_ladder(
        [(40, -450, 330), (60, -175, 145), (90, 145, -175), (100, 210, -270), (125, 650, -1100)]
    ),
}

# §3.3 -- the de-vigged survival curve those prices imply.
DOC_SURVIVAL = {40: 0.779, 60: 0.609, 74.5: 0.511, 90: 0.391, 100: 0.307, 125: 0.127}


class OddsToProbabilityTest(unittest.TestCase):
    def test_american_conversion_matches_doc(self):
        # §3.2: Over -115 -> 0.535, Under -105 -> 0.512, summing to 1.047.
        self.assertAlmostEqual(american_to_probability(-115), 0.535, places=3)
        self.assertAlmostEqual(american_to_probability(-105), 0.512, places=3)
        self.assertAlmostEqual(
            american_to_probability(-115) + american_to_probability(-105), 1.047, places=3
        )

    def test_positive_american_odds(self):
        self.assertAlmostEqual(american_to_probability(330), 100 / 430, places=6)

    def test_decimal_conversion_is_one_over_odds(self):
        self.assertAlmostEqual(decimal_to_probability(1.8), 1 / 1.8, places=9)

    def test_bad_odds_are_none_not_an_exception(self):
        for bad in (None, 0, -1.0, "n/a"):
            self.assertIsNone(decimal_to_probability(bad))


class DevigTest(unittest.TestCase):
    def test_proportional_devig_matches_doc(self):
        # §3.3: the 74.5 main line de-vigs to a fair P(over) of 0.511.
        fair = devig_proportional(american_to_probability(-115), american_to_probability(-105))
        self.assertIsNotNone(fair)
        self.assertAlmostEqual(fair[0], 0.511, places=3)
        self.assertAlmostEqual(fair[0] + fair[1], 1.0, places=9)

    def test_zero_total_is_none(self):
        self.assertIsNone(devig_proportional(0.0, 0.0))


class CollectAnchorsTest(unittest.TestCase):
    def test_reproduces_the_doc_survival_curve(self):
        anchors = collect_anchors({"bookA": DOC_RUSH_YDS_BOOK}, "player_rush_yds")
        self.assertEqual([a.threshold for a in anchors], sorted(DOC_SURVIVAL))
        for anchor in anchors:
            self.assertAlmostEqual(anchor.survival, DOC_SURVIVAL[anchor.threshold], places=3)

    def test_combines_books_by_median_not_mean(self):
        # §2.2: the median is the whole robustness story. One stale book quoting
        # a wildly different price must not drag the consensus, which a mean would.
        books = {
            "fair_a": {"player_rush_yds": two_way(50, -110, -110)},
            "fair_b": {"player_rush_yds": two_way(50, -115, -105)},
            "stale": {"player_rush_yds": two_way(50, -1000, 600)},
        }
        anchors = collect_anchors(books, "player_rush_yds")
        self.assertEqual(len(anchors), 1)
        # Median of {0.500, 0.511, 0.885}; a mean would land near 0.632.
        self.assertAlmostEqual(anchors[0].survival, 0.511, places=3)

    def test_devigs_each_book_before_combining(self):
        # Two books with identical fair prices but very different margins must
        # agree after de-vigging -- that is why de-vig comes first (§2.1).
        low_vig = collect_anchors(
            {"b": {"player_rush_yds": two_way(50, -105, -105)}}, "player_rush_yds"
        )
        high_vig = collect_anchors(
            {"b": {"player_rush_yds": two_way(50, -140, -140)}}, "player_rush_yds"
        )
        self.assertAlmostEqual(low_vig[0].survival, 0.5, places=6)
        self.assertAlmostEqual(high_vig[0].survival, 0.5, places=6)

    def test_isotonic_flattens_a_dipping_ladder(self):
        # §2.3: a noisy line must not leave the survival curve non-monotone,
        # or differencing it could produce negative probability mass.
        book = {
            "player_receptions_alternate": alt_ladder(
                [(2, -300, 240), (3, 200, -260), (4, -150, 130), (5, 400, -600)]
            )
        }
        anchors = collect_anchors({"b": book}, "player_receptions")
        survivals = [a.survival for a in anchors]
        self.assertEqual(survivals, sorted(survivals, reverse=True))

    def test_one_sided_rung_uses_the_books_own_overround(self):
        # §2.2: a one-sided alternate can't be de-vigged as a two-way market.
        # Correcting it by the book's measured margin must pull it below the
        # raw implied probability, not leave the vig in.
        book = {
            "player_rush_yds": two_way(50, -120, -120),
            "player_rush_yds_alternate": alt_ladder([(100, 300, None)]),
        }
        anchors = {a.threshold: a.survival for a in collect_anchors({"b": book}, "player_rush_yds")}
        raw = american_to_probability(300)
        self.assertLess(anchors[100], raw)
        self.assertAlmostEqual(anchors[100], raw / (2 * american_to_probability(-120)), places=6)

    def test_no_odds_yields_no_anchors(self):
        self.assertEqual(collect_anchors({}, "player_rush_yds"), [])
        self.assertEqual(collect_anchors({"b": {}}, "player_rush_yds"), [])


class ContinuousDistributionTest(unittest.TestCase):
    def setUp(self):
        self.dist = build_distribution({"bookA": DOC_RUSH_YDS_BOOK}, "player_rush_yds")

    def test_is_continuous(self):
        self.assertIsInstance(self.dist, ContinuousDistribution)

    def test_median_matches_doc(self):
        # §3.4: interpolating between the 74.5 and 90 anchors puts the median
        # at ~75.9 yards.
        self.assertAlmostEqual(self.dist.quantile(0.50), 75.9, delta=1.5)

    def test_quarter_percentile_matches_doc(self):
        # §3.4: "25th percentile ~ 43 yds by the same method."
        self.assertAlmostEqual(self.dist.quantile(0.25), 43.0, delta=3.0)

    def test_ceiling_extrapolates_past_the_top_anchor(self):
        # §3.4: F = 0.90 is beyond the 125-yard anchor (0.873), so the
        # lognormal tail carries it to ~131 yards.
        ceiling = self.dist.quantile(0.90)
        self.assertGreater(ceiling, 125.0)
        self.assertAlmostEqual(ceiling, 131.0, delta=6.0)

    def test_survival_at_anchor_matches_the_posted_line(self):
        # §3.5 prices the 100-yard bonus off P(>=100) = 0.307.
        self.assertAlmostEqual(self.dist.sf(100), 0.307, places=2)
        self.assertAlmostEqual(self.dist.sf(200), 0.007, delta=0.01)

    def test_quantiles_are_monotone_and_non_negative(self):
        previous = -1.0
        for i in range(1, 100):
            value = self.dist.quantile(i / 100.0)
            self.assertGreaterEqual(value, 0.0)
            self.assertGreaterEqual(value, previous)
            previous = value

    def test_cdf_and_quantile_are_inverses_inside_the_ladder(self):
        for q in (0.3, 0.5, 0.7, 0.85):
            self.assertAlmostEqual(self.dist.cdf(self.dist.quantile(q)), q, places=2)

    def test_equiprobable_support_averages_to_the_mean(self):
        values, weights = self.dist.support(64)
        self.assertEqual(len(values), 64)
        self.assertAlmostEqual(sum(weights), 1.0, places=9)
        self.assertAlmostEqual(
            sum(v * w for v, w in zip(values, weights, strict=True)), self.dist.mean(), delta=2.0
        )

    def test_needs_two_anchors(self):
        with self.assertRaises(ValueError):
            ContinuousDistribution([Anchor(50.0, 0.5)])


class SingleAnchorFallbackTest(unittest.TestCase):
    def test_single_threshold_still_produces_a_distribution(self):
        dist = build_distribution(
            {"b": {"player_pass_yds": two_way(249.5, -115, -105)}}, "player_pass_yds"
        )
        self.assertIsInstance(dist, ContinuousDistribution)
        self.assertLess(dist.quantile(0.10), dist.quantile(0.50))
        self.assertLess(dist.quantile(0.50), dist.quantile(0.90))

    def test_coin_flip_line_still_produces_a_spread(self):
        dist = build_distribution(
            {"b": {"player_pass_yds": two_way(250, -110, -110)}}, "player_pass_yds"
        )
        self.assertIsInstance(dist, ContinuousDistribution)
        self.assertAlmostEqual(dist.quantile(0.50), 250.0, delta=15.0)
        self.assertGreater(dist.quantile(0.90), dist.quantile(0.10))

    def test_two_books_at_different_thresholds_beat_the_fallback(self):
        # The fallback exists only while the market gives one point. A second
        # book posting a different line is real data and must be used instead.
        books = {
            "a": {"player_pass_yds": two_way(249.5, -115, -105)},
            "b": {"player_pass_yds": two_way(275.5, 140, -170)},
        }
        anchors = collect_anchors(books, "player_pass_yds")
        self.assertEqual(len(anchors), 2)


class NoisyMarketTest(unittest.TestCase):
    """Books contradicting each other must not produce an absurd curve.

    Both cases here are the same failure in different clothes: the outermost
    anchors carry no usable slope, so a lognormal fitted straight through them
    is meaningless. Left unguarded the first produced a 51-yard floor and a
    ceiling pinned to the top anchor for a 261-yard passer.
    """

    def test_books_disagreeing_about_the_lean_collapse_to_one_anchor(self):
        # Book A prices the *higher* line as the likelier over -- inconsistent,
        # so isotonic flattens both to the same probability.
        books = {
            "a": {"player_pass_yds": two_way(264.5, -112, -108)},
            "b": {"player_pass_yds": two_way(258.5, -105, -115)},
        }
        anchors = collect_anchors(books, "player_pass_yds")
        self.assertEqual(len({round(a.survival, 9) for a in anchors}), 1)

        dist = build_distribution(books, "player_pass_yds")
        floor, median, ceiling = (dist.quantile(q) for q in (0.10, 0.50, 0.90))
        self.assertAlmostEqual(median, 261.0, delta=8.0)
        self.assertGreater(floor, 0.5 * median)
        self.assertLess(ceiling, 2.0 * median)
        self.assertGreater(ceiling, 264.5)

    def test_tail_fit_walks_inward_past_near_tied_anchors(self):
        # The top two rungs are priced almost identically; the tail has to be
        # fitted from a pair that actually differs, not from those two.
        book = {
            "player_rush_yds": two_way(74.5, -115, -105),
            "player_rush_yds_alternate": alt_ladder(
                [(40, -450, 330), (100, 205, -265), (105, 210, -270)]
            ),
        }
        dist = build_distribution({"b": book}, "player_rush_yds")
        ceiling = dist.quantile(0.90)
        self.assertGreater(ceiling, 105.0)
        self.assertLess(ceiling, 300.0)

    def test_the_doc_ladder_is_unaffected_by_the_guards(self):
        dist = build_distribution({"bookA": DOC_RUSH_YDS_BOOK}, "player_rush_yds")
        self.assertAlmostEqual(dist.quantile(0.50), 75.9, delta=1.5)
        self.assertAlmostEqual(dist.quantile(0.90), 131.0, delta=6.0)


class LevelForThresholdTest(unittest.TestCase):
    def test_anytime_market_posts_no_point(self):
        # The anytime-TD market carries no point at all; it is P(>=1).
        self.assertEqual(level_for_threshold(0), 1)

    def test_half_point_line_rounds_up(self):
        self.assertEqual(level_for_threshold(0.5), 1)
        self.assertEqual(level_for_threshold(1.5), 2)
        self.assertEqual(level_for_threshold(3.5), 4)

    def test_ladder_rung_is_taken_at_face_value(self):
        # §4.1 reads a posted "2+" rung as P(>=2).
        self.assertEqual(level_for_threshold(2), 2)
        self.assertEqual(level_for_threshold(3), 3)


class CountDistributionTest(unittest.TestCase):
    def test_differencing_matches_the_doc_worked_example(self):
        # §4.2/§4.3: anytime = 0.55, 2+ = 0.18, no 3+ posted.
        dist = CountDistribution.from_anchors([Anchor(0, 0.55), Anchor(2, 0.18)])
        self.assertAlmostEqual(dist.pmf[0], 0.45, places=6)
        self.assertAlmostEqual(dist.pmf[1], 0.37, places=6)
        self.assertAlmostEqual(dist.pmf[2], 0.18, places=6)
        # §4.3 sanity check: E[count] = sum of the posted survival values.
        self.assertAlmostEqual(dist.mean(), 0.55 + 0.18, places=6)

    def test_top_bucket_is_scored_at_its_floor(self):
        # §4.2: with no higher line we don't invent the mass above the top one.
        dist = CountDistribution.from_anchors([Anchor(0, 0.55), Anchor(2, 0.18)])
        self.assertEqual(max(dist.pmf), 2)

    def test_anytime_only_collapses_to_bernoulli(self):
        # §4.4: anytime only -> 0 or 1, a hard ceiling of one unit.
        dist = CountDistribution.from_anchors([Anchor(0, 0.55)])
        self.assertEqual(sorted(dist.pmf), [0, 1])
        self.assertAlmostEqual(dist.pmf[1], 0.55, places=6)
        self.assertAlmostEqual(dist.mean(), 0.55, places=6)

    def test_a_third_line_splits_the_top_bucket(self):
        # §4.4: adding 3+ gives P(exactly 2) = P(>=2) - P(>=3) plus a 3 bucket.
        dist = CountDistribution.from_anchors([Anchor(0, 0.55), Anchor(2, 0.18), Anchor(3, 0.05)])
        self.assertAlmostEqual(dist.pmf[2], 0.13, places=6)
        self.assertAlmostEqual(dist.pmf[3], 0.05, places=6)

    def test_probabilities_sum_to_one(self):
        dist = CountDistribution.from_anchors([Anchor(0, 0.55), Anchor(2, 0.18)])
        self.assertAlmostEqual(sum(dist.pmf.values()), 1.0, places=9)

    def test_skipped_rung_leaves_mass_at_the_lower_count(self):
        # Lines at 1 and 3 with none at 2: the market never split that mass, so
        # it stays at the lower count rather than being invented into a 2.
        dist = CountDistribution.from_anchors([Anchor(0, 0.60), Anchor(3, 0.10)])
        self.assertAlmostEqual(dist.pmf[1], 0.50, places=6)
        self.assertNotIn(2, dist.pmf)

    def test_sparse_ladder_above_one_falls_back_to_a_fitted_family(self):
        # §2.3: only a line above 0.5 posted -- differencing under-determines
        # the distribution, so a count family is fitted (Poisson for now).
        dist = CountDistribution.from_anchors([Anchor(2, 0.30)])
        self.assertIsNotNone(dist)
        self.assertIn(0, dist.pmf)
        self.assertAlmostEqual(dist.sf(2), 0.30, delta=0.05)

    def test_quantiles_are_monotone(self):
        dist = CountDistribution.from_anchors([Anchor(0, 0.55), Anchor(2, 0.18)])
        self.assertLessEqual(dist.quantile(0.10), dist.quantile(0.50))
        self.assertLessEqual(dist.quantile(0.50), dist.quantile(0.90))
        self.assertEqual(dist.quantile(0.10), 0.0)
        self.assertEqual(dist.quantile(0.99), 2.0)

    def test_built_from_real_odds(self):
        book = {
            "player_pass_tds": two_way(1.5, -110, -110),
            "player_pass_tds_alternate": alt_ladder([(3, 250, -320)]),
        }
        dist = build_distribution({"b": book}, "player_pass_tds")
        self.assertIsInstance(dist, CountDistribution)
        # A 1.5 line is P(>=2), so the ladder starts above 1 and is filled.
        self.assertGreater(dist.mean(), 1.0)

    def test_empty_anchors_is_none(self):
        self.assertIsNone(CountDistribution.from_anchors([]))


class MarketClassificationTest(unittest.TestCase):
    def test_unknown_market_is_not_modeled(self):
        book = {"player_field_goals": two_way(1.5, -110, -110)}
        self.assertIsNone(build_distribution({"b": book}, "player_field_goals"))


if __name__ == "__main__":
    unittest.main()
