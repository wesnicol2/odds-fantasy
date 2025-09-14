from __future__ import annotations

from typing import Dict, Tuple, List, Optional
from statistics import median
import math


def _devig_p_over_decimal(over_odds: float | None, under_odds: float | None) -> float | None:
    try:
        o = float(over_odds) if over_odds is not None else None
        u = float(under_odds) if under_odds is not None else None
        if (o is not None) and (u is not None) and (o > 0) and (u > 0):
            o_raw = 1.0 / o
            u_raw = 1.0 / u
            tot = o_raw + u_raw
            if tot > 0:
                return o_raw / tot
        elif (o is not None) and (o > 0):
            return min(max(1.0 / o, 0.0), 1.0)
        elif (u is not None) and (u > 0):
            # Only under available; approximate S(x)=P(X>t) ~ 1 - implied_under
            pu = 1.0 / u
            return min(max(1.0 - pu, 0.0), 1.0)
    except Exception:
        pass
    return None


def _pav_isotonic(y: List[float]) -> List[float]:
    # Pool Adjacent Violators: enforce nondecreasing sequence
    # Simple implementation for small lists
    n = len(y)
    if n <= 1:
        return y[:]
    x = y[:]
    i = 0
    while i < n - 1:
        if x[i] > x[i + 1]:
            # pool back
            j = i
            while j >= 0 and x[j] > x[i + 1]:
                j -= 1
            j += 1
            val = sum(x[j:i + 2]) / float(i + 2 - j)
            for k in range(j, i + 2):
                x[k] = val
            i = max(j - 1, 0)
        else:
            i += 1
    # clamp
    for i in range(n):
        x[i] = min(max(x[i], 0.0), 1.0)
    return x


def _inverse_cdf(cdf_x: List[float], cdf_y: List[float], q: float) -> float:
    # linear interpolation over sorted cdf_x
    if not cdf_x or not cdf_y or len(cdf_x) != len(cdf_y):
        return 0.0
    if q <= cdf_y[0]:
        return cdf_x[0]
    if q >= cdf_y[-1]:
        return cdf_x[-1]
    for i in range(1, len(cdf_x)):
        if cdf_y[i] >= q:
            x0, x1 = cdf_x[i - 1], cdf_x[i]
            y0, y1 = cdf_y[i - 1], cdf_y[i]
            if y1 == y0:
                return x1
            t = (q - y0) / (y1 - y0)
            return x0 + t * (x1 - x0)
    return cdf_x[-1]


def _pchip_slopes(xs: List[float], ys: List[float]) -> List[float]:
    # Monotone cubic Hermite slopes (PCHIP) following Fritsch-Carlson/Hyman filter
    n = len(xs)
    if n <= 1:
        return [0.0] * n
    h = [xs[i+1] - xs[i] for i in range(n-1)]
    delta = [(ys[i+1] - ys[i]) / (h[i] if h[i] != 0 else 1.0) for i in range(n-1)]
    m = [0.0] * n
    # interior slopes
    for i in range(1, n-1):
        if delta[i-1] == 0.0 or delta[i] == 0.0 or (delta[i-1] * delta[i] <= 0.0):
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i-1]
            w2 = h[i] + 2.0 * h[i-1]
            m[i] = (w1 + w2) / (w1 / delta[i-1] + w2 / delta[i])
    # endpoint slopes
    m[0] = delta[0]
    if n > 2:
        m[0] = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (h[0] + h[1]) if (h[0] + h[1]) != 0 else delta[0]
        if m[0] * delta[0] < 0:
            m[0] = 0.0
        elif abs(m[0]) > 3 * abs(delta[0]):
            m[0] = 3 * delta[0]
    m[-1] = delta[-1]
    if n > 2:
        m[-1] = ((2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]) / (h[-1] + h[-2]) if (h[-1] + h[-2]) != 0 else delta[-1]
        if m[-1] * delta[-1] < 0:
            m[-1] = 0.0
        elif abs(m[-1]) > 3 * abs(delta[-1]):
            m[-1] = 3 * delta[-1]
    return m


def _pchip_inverse_cdf(cdf_x: List[float], cdf_y: List[float], q: float) -> float:
    # Invert monotone CDF using PCHIP and Newton in local segment
    n = len(cdf_x)
    if n == 0:
        return 0.0
    if n == 1:
        return cdf_x[0]
    # Clamp to bounds
    if q <= cdf_y[0]:
        return cdf_x[0]
    if q >= cdf_y[-1]:
        return cdf_x[-1]
    # find interval i with y[i] <= q <= y[i+1]
    i = 0
    for k in range(n-1):
        if cdf_y[k] <= q <= cdf_y[k+1]:
            i = k
            break
    x0, x1 = cdf_x[i], cdf_x[i+1]
    y0, y1 = cdf_y[i], cdf_y[i+1]
    h = (x1 - x0) if (x1 - x0) != 0 else 1.0
    m = _pchip_slopes(cdf_x, cdf_y)
    m0, m1 = m[i], m[i+1]
    # Solve y(t) = q, t in [0,1] via Newton starting at linear guess
    if y1 == y0:
        return x1
    t = (q - y0) / (y1 - y0)
    t = min(max(t, 0.0), 1.0)
    for _ in range(8):  # few iterations suffice
        t2 = t * t
        t3 = t2 * t
        h00 = 2*t3 - 3*t2 + 1
        h10 = t3 - 2*t2 + t
        h01 = -2*t3 + 3*t2
        h11 = t3 - t2
        y_t = h00*y0 + h10*h*m0 + h01*y1 + h11*h*m1
        dy_dt = (6*(t2 - t)*y0 + (3*t2 - 4*t + 1)*h*m0 + 6*(-t2 + t)*y1 + (3*t2 - 2*t)*h*m1)
        if dy_dt == 0:
            break
        t -= (y_t - q) / dy_dt
        if t <= 0 or t >= 1:
            # fall back to bisection-ish clamp
            t = min(max(t, 0.0), 1.0)
    return x0 + t * h


def _collect_threshold_anchors(per_bookmaker_odds: Dict, market_key: str) -> Tuple[List[float], List[float]]:
    # Returns (thresholds sorted ascending, median p_over at thresholds)
    alt_key = market_key + "_alternate"
    samples: List[Tuple[float, float]] = []
    for _book, mkts in (per_bookmaker_odds or {}).items():
        base = mkts.get(market_key) or {}
        if base:
            pt = (base.get("over") or {}).get("point")
            if pt is None:
                pt = (base.get("under") or {}).get("point")
            p_over = _devig_p_over_decimal((base.get("over") or {}).get("odds"), (base.get("under") or {}).get("odds"))
            if (pt is not None) and (p_over is not None):
                samples.append((float(pt), float(p_over)))
        alt = mkts.get(alt_key) or {}
        alts = alt.get("alts") or {}
        ov_list = alts.get("over") or []
        un_list = alts.get("under") or []
        if ov_list or un_list:
            # Pair over/under on same point where possible
            un_by_pt = {}
            for it in un_list:
                try:
                    un_by_pt[float(it.get("point"))] = float(it.get("odds"))
                except Exception:
                    continue
            for it in ov_list:
                try:
                    pt = float(it.get("point"))
                    ood = float(it.get("odds"))
                except Exception:
                    continue
                uod = un_by_pt.get(pt)
                p_over = _devig_p_over_decimal(ood, uod)
                if p_over is not None:
                    samples.append((pt, p_over))
        else:
            # Fallback: if aggregator didn't preserve alts as lists, also consider the alt market base sides
            alt_base = alt if alt else {}
            if alt_base:
                pt = (alt_base.get("over") or {}).get("point")
                if pt is None:
                    pt = (alt_base.get("under") or {}).get("point")
                p_over = _devig_p_over_decimal((alt_base.get("over") or {}).get("odds"), (alt_base.get("under") or {}).get("odds"))
                if (pt is not None) and (p_over is not None):
                    try:
                        samples.append((float(pt), float(p_over)))
                    except Exception:
                        pass

    if len(samples) < 1:
        return [], []
    by_point: Dict[float, List[float]] = {}
    for pt, p in samples:
        by_point.setdefault(pt, []).append(p)
    xs = sorted(by_point.keys())
    ps = [median(by_point[x]) for x in xs]
    # Convert survival to CDF, enforce monotonicity with PAV
    F = [min(max(1.0 - p, 0.0), 1.0) for p in ps]
    F_iso = _pav_isotonic(F)
    return xs, F_iso


def model_const_quantiles(per_bookmaker_odds: Dict, market_key: str, fallback: Tuple[float, float, float]) -> Tuple[float, float, float] | None:
    # Constantini/Piersanti: anchors → CDF via linear interpolation (after isotonic), then quantiles
    xs, F = _collect_threshold_anchors(per_bookmaker_odds, market_key)
    if len(xs) < 3:
        return None
    q15 = _inverse_cdf(xs, F, 0.15)
    q50 = _inverse_cdf(xs, F, 0.50)
    q85 = _inverse_cdf(xs, F, 0.85)
    return float(q15), float(q50), float(q85)


def model_puelz_quantiles(per_bookmaker_odds: Dict, market_key: str, fallback: Tuple[float, float, float]) -> Tuple[float, float, float] | None:
    # Puelz/Snowberg: survival anchors S(x)=p_over, F=1-S, PCHIP monotone interpolation
    xs, F = _collect_threshold_anchors(per_bookmaker_odds, market_key)
    if len(xs) < 3:
        return None
    q15 = _pchip_inverse_cdf(xs, F, 0.15)
    q50 = _pchip_inverse_cdf(xs, F, 0.50)
    q85 = _pchip_inverse_cdf(xs, F, 0.85)
    return float(q15), float(q50), float(q85)


def _is_discrete_market(market_key: str) -> bool:
    k = (market_key or "").lower()
    if k.endswith("_interceptions"):
        return True
    if "receptions" in k:
        return True
    if k.endswith("_tds"):
        return True
    return False


def _fit_lognormal_from_two_points(x1: float, f1: float, x2: float, f2: float) -> Optional[Tuple[float, float]]:
    try:
        # Inverse normal quantiles
        from statistics import NormalDist
        z1 = NormalDist().inv_cdf(min(max(f1, 1e-6), 1-1e-6))
        z2 = NormalDist().inv_cdf(min(max(f2, 1e-6), 1-1e-6))
        lx1 = math.log(max(x1, 1e-6))
        lx2 = math.log(max(x2, 1e-6))
        if z2 == z1:
            return None
        sigma = (lx2 - lx1) / (z2 - z1)
        if sigma <= 0:
            sigma = abs(sigma)
        mu = lx1 - sigma * z1
        return mu, sigma
    except Exception:
        return None


def _lognormal_quantile(mu: float, sigma: float, q: float) -> float:
    from statistics import NormalDist
    z = NormalDist().inv_cdf(min(max(q, 1e-6), 1 - 1e-6))
    return math.exp(mu + sigma * z)


def _poisson_fit_lambda(points: List[Tuple[int, float]]) -> Optional[float]:
    # Fit lambda to minimize squared CDF error at given (k, F(k)) anchor points
    if not points:
        return None
    # crude search over a reasonable range derived from anchors
    k_vals = [k for (k, _) in points]
    max_k = max(k_vals)
    # search lambda around meanish region
    lo = max(0.1, 0.3 * max_k)
    hi = max(1.0, 2.5 * max_k + 1)
    best_l = None
    best_err = 1e9
    # coarse grid then refine
    for phase in range(2):
        steps = 60 if phase == 0 else 60
        start = lo if best_l is None else max(lo, best_l * 0.5)
        end = hi if best_l is None else max(start + 1e-6, best_l * 1.5)
        for i in range(steps + 1):
            lam = start + (end - start) * i / steps
            # compute rmse
            err = 0.0
            for k, Fk in points:
                # CDF at k for Poisson
                c = 0.0
                # sum_{i<=k} e^-lam lam^i / i!
                term = math.exp(-lam)
                c = term
                for j in range(1, max(1, k) + 1):
                    term *= lam / j
                    c += term
                err += (c - Fk) ** 2
            if err < best_err:
                best_err = err
                best_l = lam
    return best_l


def model_angelini_quantiles(per_bookmaker_odds: Dict, market_key: str, fallback: Tuple[float, float, float]) -> Tuple[float, float, float] | None:
    # Angelini: PCHIP + parametric tails (yards: lognormal; discrete counts: Poisson)
    xs, F = _collect_threshold_anchors(per_bookmaker_odds, market_key)
    if len(xs) >= 4:
        # Use PCHIP within anchor range
        q15 = _pchip_inverse_cdf(xs, F, 0.15)
        q50 = _pchip_inverse_cdf(xs, F, 0.50)
        q85 = _pchip_inverse_cdf(xs, F, 0.85)
        # If any quantile is outside anchor span (due to flat segments), extend with tails
        needs_lower = (0.15 < F[0] - 1e-9)
        needs_upper = (0.85 > F[-1] + 1e-9)
        is_discrete = _is_discrete_market(market_key)
        if needs_lower:
            # Fit lower tail
            if is_discrete:
                pts = []
                for j in range(min(3, len(xs))):
                    pts.append((int(round(xs[j])), float(F[j])))
                lam = _poisson_fit_lambda(pts)
                if lam is not None:
                    # find k such that CDF(k) ~ 0.15
                    target = 0.15
                    k = 0
                    c = 0.0
                    term = math.exp(-lam)
                    c = term
                    while c < target and k < 1000:
                        k += 1
                        term *= lam / k
                        c += term
                    q15 = float(k)
            else:
                # lognormal fit using two lowest anchors
                mu_sigma = _fit_lognormal_from_two_points(max(xs[0], 1e-6), F[0], max(xs[1], 1e-6), F[1]) if len(xs) >= 2 else None
                if mu_sigma:
                    mu, sigma = mu_sigma
                    q15 = _lognormal_quantile(mu, sigma, 0.15)
        if needs_upper:
            if is_discrete:
                pts = []
                n = len(xs)
                for j in range(max(0, n - 3), n):
                    pts.append((int(round(xs[j])), float(F[j])))
                lam = _poisson_fit_lambda(pts)
                if lam is not None:
                    # invert for target 0.85
                    target = 0.85
                    # simple search
                    k = 0
                    c = 0.0
                    term = math.exp(-lam)
                    c = term
                    while c < target and k < 1000:
                        k += 1
                        term *= lam / k
                        c += term
                    q85 = float(k)
            else:
                mu_sigma = _fit_lognormal_from_two_points(max(xs[-2], 1e-6), F[-2], max(xs[-1], 1e-6), F[-1]) if len(xs) >= 2 else None
                if mu_sigma:
                    mu, sigma = mu_sigma
                    q85 = _lognormal_quantile(mu, sigma, 0.85)
        return float(q15), float(q50), float(q85)
    # Not enough anchors → fallback to Puelz → Constantini
    q = model_puelz_quantiles(per_bookmaker_odds, market_key, fallback)
    if q is not None:
        return q
    return model_const_quantiles(per_bookmaker_odds, market_key, fallback)
def get_model_registry():
    return {
        "baseline": None,  # handled by range_model fallback
        "const": model_const_quantiles,
        "puelz": model_puelz_quantiles,
        "angelini": model_angelini_quantiles,
    }
