"""
Liquidity & Sentiment — Market Regime Interpretation System
Data pipeline:  RAW → CLEANING → TRANSFORMATION → DERIVED METRICS → REGIME CLASSIFICATION → data.js

Usage:
    python3 build_dashboard.py [path/to/sentiment_n_liquidity_YYYY-MM-DD.csv]

If no path is given, the newest sentiment_n_liquidity_*.csv in the parent folder is used.
The raw CSV is only read, never modified. Output: dashboard/data.js (window.DASH = {...}).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from indicator_config import INDICATOR_CONFIG, HIDDEN_COLUMNS, READ_WORDS, PCT_ON_CHANGE, REGIME_PARAMS as RP

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
CFG = {c["key"]: c for c in INDICATOR_CONFIG}


# =============================================================================
# 1. RAW
# =============================================================================
def load_raw(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, index_col=0, parse_dates=True)
    raw.index.name = "Date"
    return raw.sort_index()


def audit(raw: pd.DataFrame) -> dict:
    cols = []
    for c in raw.columns:
        s = raw[c]
        nn = s.dropna()
        if nn.empty:
            cols.append(dict(column=c, dtype=str(s.dtype), n=0))
            continue
        first, last = nn.index.min(), nn.index.max()
        win = s.loc[first:last]
        runs = nn[nn.ne(nn.shift())]
        gap = runs.index.to_series().diff().dt.days.median() if len(runs) > 1 else None
        cols.append(dict(
            column=c, dtype=str(s.dtype), n=int(len(nn)),
            first=first.strftime("%Y-%m-%d"), last=last.strftime("%Y-%m-%d"),
            missing_total_pct=round(float(s.isna().mean() * 100), 1),
            missing_in_window_pct=round(float(win.isna().mean() * 100), 1),
            distinct_runs=int(len(runs)),
            repeat_share_pct=round(float((1 - len(runs) / len(nn)) * 100), 1),
            median_days_between_changes=None if gap is None else float(gap),
            min=None if s.dtype == object else float(nn.min()),
            max=None if s.dtype == object else float(nn.max()),
        ))
    return dict(
        rows=int(len(raw)), columns=int(raw.shape[1]),
        first_date=raw.index.min().strftime("%Y-%m-%d"), last_date=raw.index.max().strftime("%Y-%m-%d"),
        duplicate_dates=int(raw.index.duplicated().sum()), duplicate_rows=int(raw.duplicated().sum()),
        rows_without_spx=int(raw["Sentiment_SP500_Close"].isna().sum()),
        cols=cols,
    )


# =============================================================================
# 2. CLEANING  (raw kept intact; cleaned = list of genuine observations per indicator)
# =============================================================================
def clean_series(raw: pd.DataFrame, cfg: dict) -> tuple[pd.Series, dict]:
    s = raw[cfg["column"]].dropna().astype(float)
    n0 = len(s)
    if cfg["clean"] in ("collapse_runs", "drop_repeats"):
        s = s[s.ne(s.shift())]
    log = dict(rule=cfg["clean"], raw_non_null=int(n0), kept=int(len(s)), removed=int(n0 - len(s)))
    return s, log


# =============================================================================
# 3. TRANSFORMATIONS (helpers)
# =============================================================================
def pct_rank_of(value: float, hist: pd.Series) -> float:
    """Percentile rank of `value` within `hist` (mid-rank for ties), 0–100."""
    h = hist.dropna().values
    if len(h) == 0 or value is None or np.isnan(value):
        return np.nan
    return float(((h < value).sum() + 0.5 * (h == value).sum()) / len(h) * 100)


def pct_rank_series(s: pd.Series) -> pd.Series:
    """Full-sample percentile rank of every observation (descriptive, uses available history only)."""
    return s.rank(method="average", pct=True) * 100


def asof_change(s: pd.Series, days: int, tol_days: int) -> pd.Series:
    """Change vs the latest observation on/before (t − days). NaN when no observation within tolerance."""
    left = pd.DataFrame({"t": s.index - pd.Timedelta(int(days), unit="D"), "v": s.values, "d": s.index})
    right = pd.DataFrame({"t": s.index, "lag": s.values})
    m = pd.merge_asof(left.sort_values("t"), right, on="t", direction="backward",
                      tolerance=pd.Timedelta(int(tol_days), unit="D"))
    m = m.set_index("d").sort_index()
    return (m["v"] - m["lag"]).rename(s.name)


def asof_align(s: pd.Series, index: pd.DatetimeIndex, tol_days: int) -> pd.Series:
    """Explicit as-of alignment: value of latest observation on/before each date (within tolerance)."""
    left = pd.DataFrame({"t": index})
    right = pd.DataFrame({"t": s.index, "v": s.values})
    m = pd.merge_asof(left, right, on="t", direction="backward", tolerance=pd.Timedelta(int(tol_days), unit="D"))
    return pd.Series(m["v"].values, index=index)


def tol_for(cfg: dict) -> int:
    f = cfg["frequency"].lower()
    if f.startswith("monthly"):
        return 40
    if f.startswith("weekly"):
        return RP["asof_tolerance_weekly_days"]
    return RP["asof_tolerance_daily_days"]


# =============================================================================
# 4. DERIVED METRICS
# =============================================================================
def indicator_stats(key: str, s: pd.Series) -> dict:
    cfg = CFG[key]
    tol = tol_for(cfg)
    h = cfg["trend_days"]
    last_date, last = s.index[-1], float(s.iloc[-1])
    chg_h = asof_change(s, h, tol)
    chg_1m = asof_change(s, 30, tol)
    chg_1y = asof_change(s, 365, tol + 7)
    sigma = float(chg_h.dropna().std()) if chg_h.notna().sum() > 10 else np.nan
    c_h = float(chg_h.iloc[-1]) if not np.isnan(chg_h.iloc[-1]) else np.nan
    z = c_h / sigma if sigma and not np.isnan(sigma) and sigma > 0 else np.nan
    pct_on_change = key in PCT_ON_CHANGE
    pct = pct_rank_of(c_h, chg_h) if pct_on_change else pct_rank_of(last, s)

    if np.isnan(z):
        arrow, move = "?", "Insufficient data"
    elif abs(z) < RP["trend_signal_threshold"]:
        arrow, move = "→", "Stable"
    else:
        arrow, move = ("↑", "Rising") if z > 0 else ("↓", "Falling")

    # Plain-language reading of the move (from centralized READ_WORDS)
    up_w, down_w = READ_WORDS.get(key, ("Rising", "Falling"))
    risk_read = {"Rising": up_w, "Falling": down_w}.get(move, move)
    d = cfg["direction"]
    tone = 0 if move not in ("Rising", "Falling") or d == 0 else (1 if (z > 0) == (d > 0) else -1)

    flag = None
    if not np.isnan(pct):
        if pct >= RP["extreme_high_pct"]:
            flag = "Historically high" if not pct_on_change else "Unusually large rise"
        elif pct <= RP["extreme_low_pct"]:
            flag = "Historically low" if not pct_on_change else "Unusually large fall"

    def pct_chg(c):
        base = last - c
        return float(c / base * 100) if base not in (0,) and not np.isnan(c) and base > 0 else None

    first_date = s.index[0]
    years = (last_date - first_date).days / 365.25
    n = len(s)
    # Data-quality grade: coverage length + observation count
    if years >= 15 and n >= 500:
        quality = "High"
    elif years >= 4.9:
        quality = "Medium"
    else:
        quality = "Low"

    since = f"since {first_date.year}" if years >= 4.9 else f"since {first_date.strftime('%Y-%m-%d')} (~{years:.0f}Y only)"
    basis = (f"of {h}D changes {since}" if pct_on_change else f"of available history {since}")

    return dict(
        key=key, last=last, last_date=last_date.strftime("%Y-%m-%d"),
        first_date=first_date.strftime("%Y-%m-%d"), n_obs=n, years=round(years, 1),
        chg_trend=None if np.isnan(c_h) else c_h, chg_trend_pct=pct_chg(c_h), trend_days=h,
        chg_1m=None if np.isnan(chg_1m.iloc[-1]) else float(chg_1m.iloc[-1]),
        chg_1y=None if np.isnan(chg_1y.iloc[-1]) else float(chg_1y.iloc[-1]),
        chg_1y_pct=pct_chg(chg_1y.iloc[-1]) if not np.isnan(chg_1y.iloc[-1]) else None,
        trend_z=None if np.isnan(z) else round(float(z), 2), trend_arrow=arrow, trend_move=move,
        trend_read=risk_read, tone=tone, pct=None if np.isnan(pct) else round(pct), pct_on_change=pct_on_change,
        pct_basis=basis,
        hist_min=float(s.min()), hist_min_date=s.idxmin().strftime("%Y-%m-%d"),
        hist_max=float(s.max()), hist_max_date=s.idxmax().strftime("%Y-%m-%d"),
        hist_median=float(s.median()), flag=flag, quality=quality,
    )


def trend_signal_series(s: pd.Series, days: int, tol: int) -> pd.Series:
    """Δ over `days` divided by the full-history σ of that Δ (sign preserved, no mean removal)."""
    c = asof_change(s, days, tol)
    sig = c.dropna().std()
    return c / sig


def sentiment_composite(clean: dict) -> tuple[pd.DataFrame, dict]:
    """Equal-weighted average of percentile ranks (oriented so high = greed), re-ranked to 0–100."""
    idx = clean["vix"].index  # daily trading-day grid of the longest daily sentiment series
    vix_p = 100 - pct_rank_series(clean["vix"])
    aaii_p = pct_rank_series(clean["aaii"])
    pc10 = clean["pc"].rolling(RP["pc_smoothing_days"], min_periods=RP["pc_smoothing_days"]).mean()
    pc_p = 100 - pct_rank_series(pc10.dropna())
    comp = pd.DataFrame(index=idx)
    comp["vix_p"] = vix_p
    comp["aaii_p"] = asof_align(aaii_p, idx, RP["asof_tolerance_weekly_days"])
    comp["pc_p"] = pc_p.reindex(idx)  # exact-date match only, no fill
    comp["n"] = comp[["vix_p", "aaii_p", "pc_p"]].notna().sum(axis=1)
    raw_avg = comp[["vix_p", "aaii_p", "pc_p"]].mean(axis=1)
    raw_avg[comp["n"] < RP["min_components_composite"]] = np.nan
    comp["avg"] = raw_avg
    comp["score"] = pct_rank_series(raw_avg.dropna()).reindex(idx)
    meta = dict(
        components=["VIX (inverted)", "AAII Bull–Bear spread", f"Put/Call {RP['pc_smoothing_days']}D mean (inverted)"],
        coverage_from=comp["score"].first_valid_index().strftime("%Y-%m-%d"),
        full_3_from=comp.index[comp["n"] == 3][0].strftime("%Y-%m-%d"),
    )
    return comp, meta


def label_sentiment(p):
    if p is None or np.isnan(p):
        return "Insufficient Data"
    if p < RP["sentiment_fear_pct"]:
        return "Fear"
    if p > RP["sentiment_greed_pct"]:
        return "Greed"
    return "Neutral"


def label_stress(p):
    if p is None or np.isnan(p):
        return "Insufficient Data"
    if p >= RP["stress_high_pct"]:
        return "High"
    if p < RP["stress_low_pct"]:
        return "Low"
    return "Medium"


def label_trend(z, up_word, down_word, neutral_word="Neutral"):
    if z is None or np.isnan(z):
        return "Insufficient Data"
    if z > RP["trend_signal_threshold"]:
        return up_word
    if z < -RP["trend_signal_threshold"]:
        return down_word
    return neutral_word


SCORE = {  # risk-appetite vote of each component label
    "Expanding": 1, "Contracting": -1, "Easing": 1, "Tightening": -1,
    "Greed": 1, "Fear": -1, "Low": 1, "High": -1,
    "Neutral": 0, "Medium": 0,
}


def overall_label(labels: list[str]) -> str:
    valid = [l for l in labels if l in SCORE]
    if len(valid) < 3:
        return "Insufficient Data"
    votes = [SCORE[l] for l in valid]
    has_pos, has_neg = any(v > 0 for v in votes), any(v < 0 for v in votes)
    tot = sum(votes)
    if has_pos and has_neg:
        return "Mixed"
    if tot >= 2:
        return "Risk-On"
    if tot <= -2:
        return "Risk-Off"
    return "Neutral"


def segments(series: pd.Series) -> list:
    """Compress a daily label series into [start, end, label] runs for the timeline."""
    s = series.dropna()
    if s.empty:
        return []
    out, start, prev, prev_d = [], s.index[0], s.iloc[0], s.index[0]
    for d, v in s.iloc[1:].items():
        if v != prev:
            out.append([start.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d"), prev])
            start, prev = d, v
        prev_d = d
    out.append([start.strftime("%Y-%m-%d"), prev_d.strftime("%Y-%m-%d"), prev])
    return out


# =============================================================================
# helpers for JSON
# =============================================================================
def ser_to_list(s: pd.Series, dp: int = 4) -> list:
    s = s.dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), dp)] for d, v in s.items()]


def fmt_num(v, cfg_key):
    f = CFG[cfg_key]["fmt"]
    return f"{f.get('prefix', '')}{v:,.{f.get('dp', 2)}f}{f.get('suffix', '')}"


def clean_nan(o):
    if isinstance(o, dict):
        return {k: clean_nan(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean_nan(v) for v in o]
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def ordinal(n):
    n = int(round(n))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


# =============================================================================
# MAIN BUILD
# =============================================================================
def build(csv_path: str) -> dict:
    raw = load_raw(csv_path)
    aud = audit(raw)

    # ---------------- cleaning
    clean, clean_log = {}, {}
    for cfg in INDICATOR_CONFIG:
        s, log = clean_series(raw, cfg)
        clean[cfg["key"]], clean_log[cfg["key"]] = s, log

    # ---------------- per-indicator stats
    stats = {k: indicator_stats(k, s) for k, s in clean.items()}

    # ---------------- sentiment composite
    comp, comp_meta = sentiment_composite(clean)
    comp_score = comp["score"].dropna()
    comp_last = float(comp_score.iloc[-1])
    comp_last_date = comp_score.index[-1]
    comp_chg = asof_change(comp_score, 30, 7)
    comp_sig = comp_chg.dropna().std()
    comp_z = float(comp_chg.iloc[-1] / comp_sig)

    # ---------------- daily regime grid (trading days, from the CSV itself)
    grid = clean["spx"].index
    nl = clean["net_liq"]
    liq_z = trend_signal_series(nl, 91, RP["asof_tolerance_daily_days"])
    nfci_z = trend_signal_series(clean["nfci"], 91, RP["asof_tolerance_weekly_days"])
    hy_z = trend_signal_series(clean["hy"], 91, RP["asof_tolerance_daily_days"])
    vix_pct = pct_rank_series(clean["vix"])
    hy_pct = pct_rank_series(clean["hy"])

    g = pd.DataFrame(index=grid)
    g["liq_z"] = asof_align(liq_z.dropna(), grid, RP["asof_tolerance_daily_days"])
    g["nfci_z"] = asof_align(nfci_z.dropna(), grid, RP["asof_tolerance_weekly_days"])
    g["hy_z"] = asof_align(hy_z.dropna(), grid, RP["asof_tolerance_daily_days"])
    g["fc_z"] = g[["nfci_z", "hy_z"]].mean(axis=1)            # mean of available
    g["sent"] = asof_align(comp_score, grid, RP["asof_tolerance_daily_days"])
    g["vix_pct"] = asof_align(vix_pct, grid, RP["asof_tolerance_daily_days"])
    g["hy_pct"] = asof_align(hy_pct, grid, RP["asof_tolerance_daily_days"])
    g["stress_pct"] = g[["vix_pct", "hy_pct"]].mean(axis=1)   # mean of available
    g["L"] = [label_trend(z, "Expanding", "Contracting") for z in g["liq_z"]]
    g["F"] = [label_trend(-z if not np.isnan(z) else z, "Easing", "Tightening") for z in g["fc_z"]]
    g["S"] = [label_sentiment(p) for p in g["sent"]]
    g["X"] = [label_stress(p) for p in g["stress_pct"]]
    base = [overall_label([a, b, c, d]) for a, b, c, d in zip(g["L"], g["F"], g["S"], g["X"])]
    g["R0"] = base
    # Transitional: latest label differs from the dominant label of the preceding N rows
    N = RP["transitional_lookback_rows"]
    R = list(base)
    for i in range(N, len(base)):
        if base[i] == "Insufficient Data":
            continue
        window = [b for b in base[i - N:i] if b != "Insufficient Data"]
        if len(window) >= N // 2:
            mode = max(set(window), key=window.count)
            share = window.count(base[i]) / len(window)
            if mode != base[i] and share < 0.5:
                R[i] = "Transitional"
    g["R"] = R

    last = g.iloc[-1]
    prior_mode = None
    win = [b for b in g["R0"].iloc[-N - 1:-1] if b != "Insufficient Data"]
    if win:
        prior_mode = max(set(win), key=win.count)

    # ---------------- liquidity components: weekly contributions (Wednesday as-of)
    wed = pd.date_range(nl.index[0], nl.index[-1], freq="W-WED")
    fa_w = asof_align(clean["fed_assets"], wed, RP["asof_tolerance_weekly_days"])
    tga_w = asof_align(clean["tga"], wed, RP["asof_tolerance_daily_days"])
    rrp_w = asof_align(clean["rrp"], wed, RP["asof_tolerance_daily_days"])
    contrib = pd.DataFrame({"fed_assets": fa_w.diff(), "tga": -tga_w.diff(), "rrp": -rrp_w.diff()}, index=wed)
    contrib["net"] = contrib.sum(axis=1, min_count=3)
    contrib = contrib.dropna()

    # 13-week attribution for the headline explanation
    def asof_val(s, d, tol):
        sub = s.loc[:d]
        if sub.empty or (d - sub.index[-1]).days > tol:
            return np.nan
        return float(sub.iloc[-1])
    end_d = nl.index[-1]
    start_d = end_d - pd.Timedelta(days=91)
    attr = {}
    for k, sign in (("fed_assets", 1), ("tga", -1), ("rrp", -1)):
        tol = tol_for(CFG[k])
        attr[k] = sign * (asof_val(clean[k], end_d, tol) - asof_val(clean[k], start_d, tol))
    attr["net"] = asof_val(nl, end_d, 7) - asof_val(nl, start_d, 7)

    # ---------------- liquidity × sentiment relationship (weekly, Friday last obs; no fill)
    wk_nl = nl.resample("W-FRI").last()
    wk_cs = comp_score.resample("W-FRI").last()
    wk = pd.DataFrame({"nl": wk_nl, "cs": wk_cs}).dropna()
    d_nl, d_cs = wk["nl"].diff(), wk["cs"].diff()
    corr = {f"{w}W": d_nl.rolling(w, min_periods=int(w * 0.8)).corr(d_cs) for w in (13, 26, 52)}
    lvl_corr_52 = wk["nl"].rolling(52, min_periods=40).corr(wk["cs"])
    nl_pct = pct_rank_series(nl)
    wk_q = pd.DataFrame({
        "x_pct": nl_pct.resample("W-FRI").last(),
        "x_z": liq_z.resample("W-FRI").last(),
        "y": wk_cs,
    }).dropna()

    def corr_label(r):
        if r is None or np.isnan(r):
            return "Insufficient data"
        a = abs(r)
        strength = "Weak" if a < 0.3 else ("Moderate" if a < 0.6 else "Strong")
        if strength == "Weak":
            return "Weak relationship"
        return f"{strength} {'positive' if r > 0 else 'negative'} co-movement"

    corr_now = {k: (None if np.isnan(v.dropna().iloc[-1]) else round(float(v.dropna().iloc[-1]), 2))
                if v.notna().any() else None for k, v in corr.items()}

    # ---------------- stress monitor
    stress_now = dict(
        vix_pct=stats["vix"]["pct"], hy_pct=stats["hy"]["pct"],
        stress_pct=None if np.isnan(last["stress_pct"]) else round(float(last["stress_pct"])),
        label=last["X"],
    )

    # ---------------- regime summary (current)
    liq_z_now = float(last["liq_z"])
    fc_z_now = float(last["fc_z"])
    nfci_lvl = stats["nfci"]["last"]
    reasons = dict(
        liquidity=(f"Net Liquidity {('+' if attr['net'] >= 0 else '−')}${abs(attr['net']):,.0f}bn over ~3M "
                   f"(signal {liq_z_now:+.2f}σ; threshold ±{RP['trend_signal_threshold']}σ). "
                   f"Drivers: Fed assets {attr['fed_assets']:+,.0f}bn, TGA {attr['tga']:+,.0f}bn, "
                   f"RRP {attr['rrp']:+,.0f}bn (signed as contribution)."),
        financial=(f"NFCI {nfci_lvl:+.3f} ({'looser' if nfci_lvl < 0 else 'tighter'} than its 1971+ average), "
                   f"3M change {stats['nfci']['chg_trend']:+.3f}; HY OAS {stats['hy']['last']:.2f}% "
                   f"({stats['hy']['chg_trend']:+.2f}pp over 3M). Combined change signal {fc_z_now:+.2f}σ."),
        sentiment=(f"Composite at {ordinal(comp_last)} percentile of its history "
                   f"(Fear < {RP['sentiment_fear_pct']}, Greed > {RP['sentiment_greed_pct']}). "
                   f"VIX {stats['vix']['last']:.1f}, AAII {stats['aaii']['last']:+.1f}pp, "
                   f"P/C {stats['pc']['last']:.2f}; CNN F&G cross-check {stats['cnn']['last']:.0f}."),
        stress=(f"Stress percentile {stress_now['stress_pct']} = mean of VIX pct {stats['vix']['pct']} "
                f"(since 1990) and HY OAS pct {stats['hy']['pct']} (since 2023 only). "
                f"Low < {RP['stress_low_pct']}, High ≥ {RP['stress_high_pct']}."),
    )

    short = [CFG[k]["name"] for k in ("net_liq", "nfci", "hy") if stats[k]["years"] < 4.9]
    conf = "High" if not short else ("Medium" if len(short) <= 3 else "Low")
    conf_note = (("Short history: " + ", ".join(short) + f" start {stats['net_liq']['first_date']} in this CSV (~3Y). "
                  "Their percentiles describe a QT-era window, not a full cycle; VIX / AAII / Put-Call have 30Y+.")
                 if short else "All regime inputs have ≥ 5 years of history.")
    recent = [b for b in g["R0"].iloc[-N:]]
    recent_counts = {k: recent.count(k) for k in dict.fromkeys(recent)}

    regime_now = dict(
        date=grid[-1].strftime("%Y-%m-%d"),
        overall=last["R"], base=last["R0"], prior_dominant=prior_mode,
        components=dict(
            liquidity=dict(label=last["L"], signal=round(liq_z_now, 2), reason=reasons["liquidity"]),
            financial=dict(label=last["F"], signal=round(fc_z_now, 2), reason=reasons["financial"]),
            sentiment=dict(label=last["S"], signal=round(comp_last), reason=reasons["sentiment"],
                           trend=label_trend(comp_z, "Improving", "Weakening", "Stable")),
            stress=dict(label=last["X"], signal=stress_now["stress_pct"], reason=reasons["stress"]),
        ),
        confidence=conf,
        confidence_note=conf_note,
        recent_base=recent_counts,
        recent_window=N,
    )

    # Interpretation sentences (observations only — no predictions)
    def dir_word(z):
        return "risen" if z > 0 else "fallen"
    interp = dict(
        net_liq=(f"Net liquidity has {dir_word(attr['net'])} by ${abs(attr['net']):,.0f}bn over the past ~3 months; "
                 f"the move is {'within normal noise' if abs(liq_z_now) < RP['trend_signal_threshold'] else 'larger than typical'} "
                 f"({liq_z_now:+.2f}σ). It sits at the {ordinal(stats['net_liq']['pct'])} percentile of its 3-year available history."),
        components=("The largest 3-month contribution came from "
                    + max((('Fed balance sheet', attr['fed_assets']), ('TGA', attr['tga']), ('RRP', attr['rrp'])),
                          key=lambda t: abs(t[1]))[0]
                    + f" ({max(attr['fed_assets'], attr['tga'], attr['rrp'], key=abs):+,.0f}bn). "
                      f"RRP balance is ${stats['rrp']['last']:,.1f}bn — "
                    + ("effectively exhausted, so it can no longer offset QT/TGA drains."
                       if stats['rrp']['last'] < 50 else "still providing a buffer.")),
        sentiment=(f"The sentiment composite is at the {ordinal(comp_last)} percentile ({last['S']}). "
                   f"VIX is at the {ordinal(stats['vix']['pct'])} percentile since 1990; "
                   f"CNN Fear & Greed reads {stats['cnn']['last']:.0f}."),
        financial=(f"NFCI remains {'below' if nfci_lvl < 0 else 'above'} zero (conditions {'looser' if nfci_lvl < 0 else 'tighter'} "
                   f"than the 1971+ average). HY spreads are {stats['hy']['last']:.2f}%, "
                   f"{'up' if stats['hy']['chg_trend'] > 0 else 'down'} {abs(stats['hy']['chg_trend']):.2f}pp over 3M."),
        relationship=(f"Over the last 26 weeks, weekly changes in liquidity and sentiment show: "
                      f"{corr_label(corr_now.get('26W')).lower()} (r = {corr_now.get('26W')}). "
                      "Correlation describes co-movement only — it does not imply causation."),
        stress=(f"Market stress is {last['X'].lower()}: VIX at the {ordinal(stats['vix']['pct'])} percentile, "
                f"HY OAS at the {ordinal(stats['hy']['pct'])} percentile of its short available window."),
    )

    # ---------------- detail table (actual observations only; blanks = no observation that day)
    tbl_idx = raw.index
    T = pd.DataFrame(index=tbl_idx)
    for k in ("spx", "net_liq", "vix", "aaii", "pc", "cnn", "nfci", "hy", "fed_assets", "tga", "rrp", "effr", "breadth", "margin"):
        T[k] = clean[k].reindex(tbl_idx)
    T["nl_chg13w"] = asof_change(nl, 91, 7).reindex(tbl_idx)
    T["sent_comp"] = comp["score"].reindex(tbl_idx)
    T["stress"] = g["X"].reindex(tbl_idx)
    T["regime"] = g["R"].reindex(tbl_idx)
    T = T.replace({"Insufficient Data": None})
    dps = dict(spx=2, net_liq=1, vix=2, aaii=1, pc=2, cnn=1, nfci=3, hy=2, fed_assets=1, tga=1, rrp=2,
               effr=2, breadth=4, margin=0, nl_chg13w=1, sent_comp=0)
    rows = []
    for d, r in T.iterrows():
        row = [d.strftime("%Y-%m-%d")]
        for c in T.columns:
            v = r[c]
            if isinstance(v, str):
                row.append(v)
            elif v is None or (isinstance(v, float) and np.isnan(v)):
                row.append(None)
            else:
                row.append(round(float(v), dps.get(c, 2)))
        rows.append(row)
    table = dict(columns=["date"] + list(T.columns), rows=rows)

    # ---------------- matrix (Current vs Historical)
    matrix_keys = ["net_liq", "fed_assets", "tga", "rrp", "nfci", "hy", "vix", "aaii", "pc", "cnn", "margin", "breadth", "effr"]
    matrix = []
    for k in matrix_keys:
        st = stats[k]
        matrix.append(dict(key=k, **{x: st[x] for x in (
            "last", "last_date", "trend_arrow", "trend_move", "trend_read", "pct", "pct_basis", "flag",
            "quality", "first_date", "chg_trend", "chg_1y", "trend_days")}))
    matrix.insert(0, dict(key="sent_comp", last=round(comp_last), last_date=comp_last_date.strftime("%Y-%m-%d"),
                          trend_arrow="→" if abs(comp_z) < RP["trend_signal_threshold"] else ("↑" if comp_z > 0 else "↓"),
                          trend_move=label_trend(comp_z, "Rising", "Falling", "Stable"),
                          trend_read=label_trend(comp_z, "Improving", "Deteriorating", "Stable"),
                          pct=round(comp_last), pct_basis="score is itself a percentile (since 1990)",
                          flag=None, quality="Medium", first_date=comp_meta["coverage_from"],
                          chg_trend=float(comp_chg.iloc[-1]), chg_1y=None, trend_days=30))

    # ---------------- methodology (rendered verbatim in the UI)
    methodology = [
        dict(title="Data cleaning — undoing upstream forward-fill",
             body=["The source CSV is a daily outer-join of mixed-frequency series; the upstream pipeline forward-filled weekly "
                   "and some daily series. The raw file is never modified; cleaning happens only in this pipeline.",
                   "collapse_runs (WALCL, NFCI, AAII): keep only the first date of each new value — the observation's "
                   "reference/release date. Weekly data are therefore plotted as weekly points, not as a daily line.",
                   "drop_repeats (Net Liquidity, TGA, RRP, HY OAS, CNN F&G): consecutive identical values are treated as carried "
                   "forward and removed. A genuinely unchanged print would also be dropped; impact on trends/percentiles is negligible.",
                   "none (S&P 500, VIX, Put/Call, EFFR, Breadth, FINRA): values kept as delivered (2-decimal quotes can legitimately repeat).",
                   "Missing values are never treated as 0, never interpolated, and lines are not drawn across gaps longer than the native frequency.",
                   "Net Liquidity is provided pre-computed in the CSV (WALCL − TGA − RRP; identity verified to 0.0 error). Between Wednesdays it "
                   "uses the latest weekly WALCL — this upstream carry-forward is disclosed, not hidden."]),
        dict(title="Historical percentile",
             body=["Percentile rank = (count below + ½ count equal) ÷ number of genuine observations, over each indicator's own available history. "
                   "Missing periods are excluded from the denominator. Weekly series are ranked on weekly observations only.",
                   "Every percentile is shown with its observation period (e.g. 'since 1990' or 'since 2023-10-17 (~3Y only)'). "
                   "Indicators with < 5 years of history are labelled Low data quality.",
                   f"Extreme flags: ≥ {RP['extreme_high_pct']}th percentile = historically high; ≤ {RP['extreme_low_pct']}th = historically low.",
                   "Historical percentile time-series (composite, stress) use the full available sample — descriptive, not a real-time backtest."]),
        dict(title="Trend signal (used for Liquidity and Financial Conditions)",
             body=["Δ = latest value − value on/before (t − horizon) using as-of lookup (no filling). Horizon: 91 calendar days (~3M) for "
                   "liquidity/credit/NFCI/AAII, 30 days for daily market sentiment, 365 days for monthly FINRA data.",
                   "Signal = Δ ÷ σ(Δ), σ = standard deviation of all historical Δ at the same horizon (sign preserved, no mean removal).",
                   f"|signal| < {RP['trend_signal_threshold']} → Stable/Neutral; above → Rising/Falling. This scales each indicator by its own typical move "
                   "instead of an arbitrary absolute threshold."]),
        dict(title="Sentiment Composite",
             body=["Components: VIX (inverted), AAII Bull–Bear spread, CBOE Total Put/Call 10-day mean (inverted).",
                   "Normalization: each component → full-history percentile rank (oriented: high = greed).",
                   "Weighting: equal-weighted mean of available components (min 2 of 3), then re-ranked to a 0–100 percentile of the composite's own history.",
                   "Alignment: daily VIX trading-day grid; weekly AAII aligned as-of (latest released survey, ≤ 12 days old); Put/Call exact-date only.",
                   f"Coverage: from {comp_meta['coverage_from']} (all 3 components from {comp_meta['full_3_from']}).",
                   "CNN Fear & Greed is NOT included (only since 2021 and it already embeds VIX, Put/Call and junk-bond demand) — it is shown as an independent cross-check.",
                   "Breadth (RSP/SPY) excluded: its level drifts structurally and it measures participation, not sentiment.",
                   f"Regime: < {RP['sentiment_fear_pct']} Fear, > {RP['sentiment_greed_pct']} Greed, otherwise Neutral. Displayed as an integer; decimals would be false precision."]),
        dict(title="Liquidity Composite — deliberately NOT created",
             body=["Only ~3 years of liquidity data, mixed weekly/daily frequency, and NFCI/HY measure conditions rather than quantity. "
                   "A numeric 'Liquidity Score' would be false precision. Liquidity is reported as Expanding / Neutral / Contracting from the Net Liquidity trend signal only."]),
        dict(title="Regime classification rules",
             body=[f"Liquidity: Net Liquidity 3M trend signal > +{RP['trend_signal_threshold']} Expanding, < −{RP['trend_signal_threshold']} Contracting, else Neutral.",
                   f"Financial Conditions: mean of NFCI 3M signal and HY OAS 3M signal (available ones); < −{RP['trend_signal_threshold']} Easing, > +{RP['trend_signal_threshold']} Tightening, else Neutral. "
                   "NFCI level vs 0 is shown as context (by construction 0 = 1971+ average).",
                   "Sentiment: composite percentile thresholds above.",
                   f"Market Stress: mean of VIX percentile (since 1990) and HY OAS percentile (since 2023-10); < {RP['stress_low_pct']} Low, ≥ {RP['stress_high_pct']} High, else Medium.",
                   "Overall: each component votes +1 (Expanding / Easing / Greed / Low stress), −1 (Contracting / Tightening / Fear / High stress) or 0.",
                   "Risk-On = sum ≥ +2 with no −1 vote · Risk-Off = sum ≤ −2 with no +1 vote · Mixed = at least one +1 AND one −1 · Neutral = otherwise.",
                   f"Transitional = today's label differs from the dominant label of the previous {RP['transitional_lookback_rows']} trading days and occurred in < 50% of them.",
                   "Insufficient Data = fewer than 3 components available (e.g. before 2023-10 when liquidity/NFCI/HY are absent).",
                   "Daily regime history uses explicit as-of alignment (latest observation within tolerance: 7 days daily, 12 days weekly)."]),
        dict(title="Liquidity × Sentiment relationship",
             body=["Weekly sampling (last genuine observation each Friday week; no fill). Rolling Pearson correlation of weekly changes over 13W (~90D), 26W and 52W (~1Y).",
                   "A 30-day window is not offered: with weekly sampling it would contain only ~4 points.",
                   "|r| < 0.3 = Weak relationship (not interpreted), 0.3–0.6 Moderate, ≥ 0.6 Strong. Correlation ≠ causation."]),
        dict(title="Interpretation boundary",
             body=["This is a market-analysis tool, not a prediction engine. Text describes observed conditions, historical context, trends and statistical relationships only."]),
    ]

    # ---------------- coverage / dictionary
    dictionary = []
    for cfg in INDICATOR_CONFIG:
        st = stats[cfg["key"]]
        a = next(c for c in aud["cols"] if c["column"] == cfg["column"])
        dictionary.append(dict(
            key=cfg["key"], column=cfg["column"], name=cfg["name"], category=cfg["category"], meaning=cfg["meaning"],
            unit=cfg["unit"], frequency=cfg["frequency"], available_from=st["first_date"], available_to=st["last_date"],
            missing_in_window_pct=a["missing_in_window_pct"], missing_total_pct=a["missing_total_pct"],
            interp_high=cfg["interp_high"], interp_low=cfg["interp_low"], priority=cfg["priority"],
            clean=cfg["clean"], clean_removed=clean_log[cfg["key"]]["removed"], n_obs=st["n_obs"],
            quality=st["quality"], direction=cfg["direction"], fmt=cfg["fmt"], trend_days=cfg["trend_days"],
        ))

    # ---------------- assemble
    series_dp = dict(spx=2, net_liq=1, fed_assets=1, tga=1, rrp=2, nfci=3, hy=2, vix=2, aaii=2, pc=2, cnn=1,
                     breadth=4, margin=0, free_cash=0, free_margin=0, effr=2)
    out = dict(
        meta=dict(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"), source_file=os.path.basename(csv_path),
                  latest_date=grid[-1].strftime("%Y-%m-%d"), first_date=aud["first_date"]),
        params=RP,
        audit=aud, clean_log=clean_log, hidden=HIDDEN_COLUMNS,
        dictionary=dictionary, stats=stats,
        series={k: ser_to_list(s, series_dp.get(k, 4)) for k, s in clean.items()},
        derived=dict(
            pc10=ser_to_list(clean["pc"].rolling(RP["pc_smoothing_days"], min_periods=RP["pc_smoothing_days"]).mean(), 3),
            comp=ser_to_list(comp["score"], 1),
            comp_components=dict(vix_p=ser_to_list(comp["vix_p"], 1), aaii_p=ser_to_list(comp["aaii_p"], 1),
                                 pc_p=ser_to_list(comp["pc_p"], 1)),
            comp_meta=comp_meta,
            nl_pct=ser_to_list(nl_pct, 1), vix_pct=ser_to_list(vix_pct, 1), hy_pct=ser_to_list(hy_pct, 1),
            liq_z=ser_to_list(liq_z, 2), fc_z=ser_to_list(g["fc_z"], 2), stress_pct=ser_to_list(g["stress_pct"], 1),
            contrib=[[d.strftime("%Y-%m-%d"), round(r.fed_assets, 1), round(r.tga, 1), round(r.rrp, 1), round(r.net, 1)]
                     for d, r in contrib.iterrows()],
            attr_3m={k: round(float(v), 1) for k, v in attr.items()},
            corr={k: ser_to_list(v, 3) for k, v in corr.items()}, corr_now=corr_now,
            corr_label={k: corr_label(v) for k, v in corr_now.items()},
            lvl_corr_52=ser_to_list(lvl_corr_52, 3),
            quadrant=[[d.strftime("%Y-%m-%d"), round(r.x_pct, 1), round(r.x_z, 2), round(r.y, 1)] for d, r in wk_q.iterrows()],
            vix_quantiles={str(q): round(float(clean["vix"].quantile(q / 100)), 2) for q in (10, 50, 80, 90)},
            hy_quantiles={str(q): round(float(clean["hy"].quantile(q / 100)), 2) for q in (10, 50, 80, 90)},
        ),
        regimes=dict(
            liquidity=segments(g["L"].where(g["L"] != "Insufficient Data")),
            financial=segments(g["F"].where(g["F"] != "Insufficient Data")),
            sentiment=segments(asof_align(comp_score, grid, 7).dropna().map(label_sentiment)),
            stress=segments(g["X"].where(g["X"] != "Insufficient Data")),
            overall=segments(g["R"].where(g["R"] != "Insufficient Data")),
        ),
        regime_now=regime_now, stress_now=stress_now, interp=interp, matrix=matrix,
        methodology=methodology, table=table,
    )
    return clean_nan(out)


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(glob.glob(os.path.join(PROJECT, "sentiment_n_liquidity_20*.csv")))
        files = [f for f in files if not f.endswith("_status.csv")]
        path = files[-1]
    print(f"[build] source: {path}")
    data = build(path)
    js = "window.DASH = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    out = os.path.join(HERE, "data.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write(js)
    rn = data["regime_now"]
    print(f"[build] wrote {out} ({len(js) / 1e6:.2f} MB)")
    print(f"[build] {rn['date']}  OVERALL = {rn['overall']} (base {rn['base']}, prior dominant {rn['prior_dominant']})")
    for k, v in rn["components"].items():
        print(f"        {k:<10} {v['label']:<12} signal={v['signal']}")


if __name__ == "__main__":
    main()
