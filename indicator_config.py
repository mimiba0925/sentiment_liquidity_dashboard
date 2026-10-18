"""
Centralized INDICATOR_CONFIG for the Liquidity & Sentiment Market Regime Dashboard.

Every indicator shown anywhere in the dashboard is defined here. The UI reads this
config (exported to data.js) so adding / editing an indicator does not require UI edits.

Field reference
---------------
key            internal id
column         original CSV column name (raw data is never modified)
name           display name
category       Liquidity / Sentiment / Financial Conditions / Market / Credit / Other
meaning        what the indicator represents
unit           display unit
frequency      native frequency of the *underlying* data (not the CSV row frequency)
clean          cleaning rule applied in the data-cleaning layer:
                 "none"          keep every non-null value
                 "collapse_runs" weekly/monthly data that was forward-filled upstream
                                 onto a daily grid -> keep only the first date of each
                                 new value (= the reference date of the observation)
                 "drop_repeats"  high-precision daily data where upstream merging
                                 forward-filled holidays / the latest day -> drop
                                 consecutive exact duplicates
direction      how a RISE should be read in risk-appetite terms:
                 +1  rise = risk-on / easier / more optimism
                 -1  rise = risk-off / tighter / more fear or stress
                  0  context only (no risk direction)
priority       Core / Secondary / Detail / Hidden
fmt            number format hint for the UI: {"dp": decimals, "prefix", "suffix"}
trend_days     calendar-day horizon used for the trend (change) signal
interp_high / interp_low   what high / low values usually mean
"""

INDICATOR_CONFIG = [
    # ---------------------------------------------------------------- LIQUIDITY
    dict(key="net_liq", column="Liquidity_Net_Liquidity", name="Net Liquidity",
         category="Liquidity",
         meaning="Fed total assets (WALCL) − Treasury General Account (TGA) − ON Reverse Repo (RRP). "
                 "Proxy for USD liquidity available to the financial system.",
         unit="USD bn", frequency="Daily (derived upstream; weekly WALCL carried forward between Wednesdays)",
         clean="drop_repeats", direction=+1, priority="Core",
         fmt=dict(dp=0, prefix="$", suffix="bn"), trend_days=91,
         interp_high="More reserves / liquidity in the system",
         interp_low="Liquidity being drained (QT, TGA rebuild, RRP inflows)"),
    dict(key="fed_assets", column="Liquidity_Fed_Assets_B", name="Fed Total Assets (WALCL)",
         category="Liquidity", meaning="Federal Reserve balance-sheet size (H.4.1, Wednesday level).",
         unit="USD bn", frequency="Weekly (Wed)", clean="collapse_runs", direction=+1, priority="Secondary",
         fmt=dict(dp=0, prefix="$", suffix="bn"), trend_days=91,
         interp_high="Larger balance sheet adds liquidity", interp_low="QT / balance-sheet runoff drains liquidity"),
    dict(key="tga", column="Liquidity_TGA", name="Treasury General Account (TGA)",
         category="Liquidity", meaning="US Treasury cash balance at the Fed (Daily Treasury Statement).",
         unit="USD bn", frequency="Daily (business days)", clean="drop_repeats", direction=-1, priority="Secondary",
         fmt=dict(dp=0, prefix="$", suffix="bn"), trend_days=91,
         interp_high="Treasury is holding cash → drains bank reserves",
         interp_low="Treasury spending down cash → adds reserves"),
    dict(key="rrp", column="Liquidity_Reverse_Repo", name="ON Reverse Repo (RRP)",
         category="Liquidity", meaning="Cash parked at the Fed's overnight reverse-repo facility.",
         unit="USD bn", frequency="Daily (business days)", clean="drop_repeats", direction=-1, priority="Secondary",
         fmt=dict(dp=1, prefix="$", suffix="bn"), trend_days=91,
         interp_high="Idle cash sitting outside the banking system",
         interp_low="RRP buffer depleted (near zero = no more cushion to release)"),
    # ---------------------------------------------------- FINANCIAL CONDITIONS / CREDIT
    dict(key="nfci", column="Liquidity_NFCI", name="Chicago Fed NFCI",
         category="Financial Conditions",
         meaning="National Financial Conditions Index. Constructed with mean 0 / std 1 over 1971–present; "
                 "negative = looser than average, positive = tighter than average.",
         unit="index (std dev)", frequency="Weekly (week ending Fri)", clean="collapse_runs", direction=-1,
         priority="Core", fmt=dict(dp=3), trend_days=91,
         interp_high="Tighter-than-average financial conditions", interp_low="Looser-than-average financial conditions"),
    dict(key="hy", column="Liquidity_HY_Spread", name="High-Yield OAS",
         category="Credit", meaning="ICE BofA US High Yield option-adjusted spread (FRED BAMLH0A0HYM2).",
         unit="%", frequency="Daily (business days)", clean="drop_repeats", direction=-1, priority="Core",
         fmt=dict(dp=2, suffix="%"), trend_days=91,
         interp_high="Credit stress / risk aversion", interp_low="Tight spreads, strong risk appetite (possible complacency)"),
    # ---------------------------------------------------------------- SENTIMENT
    dict(key="vix", column="Sentiment_VIX", name="VIX",
         category="Sentiment", meaning="CBOE S&P 500 30-day implied volatility.",
         unit="index pts", frequency="Daily (trading days)", clean="none", direction=-1, priority="Core",
         fmt=dict(dp=2), trend_days=30,
         interp_high="Fear / demand for protection / market stress", interp_low="Calm, complacent markets"),
    dict(key="aaii", column="Sentiment_AAII_Spread", name="AAII Bull–Bear Spread",
         category="Sentiment", meaning="AAII weekly survey: % bullish − % bearish retail investors.",
         unit="pp", frequency="Weekly (Thu)", clean="collapse_runs", direction=+1, priority="Secondary",
         fmt=dict(dp=1, suffix="pp"), trend_days=91,
         interp_high="Retail optimism", interp_low="Retail pessimism"),
    dict(key="pc", column="Sentiment_PC_Ratio", name="CBOE Total Put/Call",
         category="Sentiment", meaning="CBOE total put volume / call volume (daily).",
         unit="ratio", frequency="Daily (trading days)", clean="none", direction=-1, priority="Secondary",
         fmt=dict(dp=2), trend_days=30,
         interp_high="Hedging / bearish positioning", interp_low="Call speculation / bullish positioning"),
    dict(key="cnn", column="Sentiment_CNN_FearGreed", name="CNN Fear & Greed",
         category="Sentiment",
         meaning="CNN composite of 7 sentiment inputs (0 = extreme fear, 100 = extreme greed). "
                 "Overlaps with VIX, Put/Call and HY spread, so used as a cross-check only.",
         unit="0–100", frequency="Daily", clean="drop_repeats", direction=+1, priority="Secondary",
         fmt=dict(dp=0), trend_days=30,
         interp_high="Greed", interp_low="Fear"),
    dict(key="breadth", column="Sentiment_Breadth_Ratio", name="Breadth Proxy (RSP/SPY)",
         category="Market",
         meaning="Equal-weight / cap-weight S&P 500 ETF price ratio. A falling ratio means mega-caps "
                 "are outperforming the average stock (narrowing breadth). Level drifts structurally, so "
                 "only its change is meaningful.",
         unit="ratio", frequency="Daily (trading days)", clean="none", direction=+1, priority="Detail",
         fmt=dict(dp=4), trend_days=91,
         interp_high="Broad participation", interp_low="Narrow, mega-cap-led market"),
    dict(key="margin", column="Liquidity_Margin_Debit Balances in Customers' Securities Margin Accounts",
         name="FINRA Margin Debt", category="Sentiment",
         meaning="Debit balances in customers' securities margin accounts (investor leverage). "
                 "Stamped on the 1st of the reference month.",
         unit="USD mn", frequency="Monthly", clean="none", direction=+1, priority="Detail",
         fmt=dict(dp=0, prefix="$", suffix="mn"), trend_days=365,
         interp_high="High investor leverage / risk appetite", interp_low="De-leveraging"),
    dict(key="free_cash", column="Liquidity_Margin_Free Credit Balances in Customers' Cash Accounts",
         name="FINRA Free Credit (Cash Accts)", category="Liquidity",
         meaning="Free credit balances in customers' cash accounts (idle investor cash).",
         unit="USD mn", frequency="Monthly", clean="none", direction=0, priority="Detail",
         fmt=dict(dp=0, prefix="$", suffix="mn"), trend_days=365,
         interp_high="More idle cash at brokers", interp_low="Cash deployed"),
    dict(key="free_margin", column="Liquidity_Margin_Free Credit Balances in Customers' Securities Margin Accounts",
         name="FINRA Free Credit (Margin Accts)", category="Liquidity",
         meaning="Free credit balances in customers' securities margin accounts.",
         unit="USD mn", frequency="Monthly", clean="none", direction=0, priority="Detail",
         fmt=dict(dp=0, prefix="$", suffix="mn"), trend_days=365,
         interp_high="More idle cash at brokers", interp_low="Cash deployed"),
    # ---------------------------------------------------------------- CONTEXT
    dict(key="spx", column="Sentiment_SP500_Close", name="S&P 500",
         category="Market", meaning="S&P 500 index close (context only; not used in any regime rule).",
         unit="index", frequency="Daily (trading days)", clean="none", direction=0, priority="Detail",
         fmt=dict(dp=0), trend_days=91, interp_high="—", interp_low="—"),
    dict(key="effr", column="Sentiment_Fed_Rate", name="Effective Fed Funds Rate",
         category="Other", meaning="NY Fed Effective Federal Funds Rate (policy-rate context).",
         unit="%", frequency="Daily (business days)", clean="none", direction=0, priority="Detail",
         fmt=dict(dp=2, suffix="%"), trend_days=91,
         interp_high="Restrictive policy level", interp_low="Accommodative policy level"),
]

# Plain-language reading of a significant rise / fall (used in the matrix "Status" column).
READ_WORDS = {
    "net_liq": ("Liquidity improving", "Liquidity draining"),
    "fed_assets": ("Balance sheet growing", "Balance sheet shrinking (QT)"),
    "tga": ("Rising — drains reserves", "Falling — adds reserves"),
    "rrp": ("Rising — cash parked at Fed", "Falling — cash released"),
    "nfci": ("Tightening", "Easing"),
    "hy": ("Widening — more credit stress", "Tightening — less credit stress"),
    "vix": ("Rising — more fear", "Falling — calmer"),
    "aaii": ("More optimistic", "More pessimistic"),
    "pc": ("More hedging", "Less hedging"),
    "cnn": ("Toward greed", "Toward fear"),
    "breadth": ("Broadening", "Narrowing (mega-cap led)"),
    "margin": ("Leverage rising", "De-leveraging"),
    "free_cash": ("Idle cash rising", "Idle cash falling"),
    "free_margin": ("Idle cash rising", "Idle cash falling"),
    "spx": ("Rising", "Falling"),
    "effr": ("Policy rate rising", "Policy rate falling"),
}

# Indicators whose LEVEL drifts structurally -> percentile is computed on the trend-horizon change.
PCT_ON_CHANGE = {"breadth"}

# Columns present in the CSV that are intentionally NOT visualized (documented in the UI).
HIDDEN_COLUMNS = {
    "Liquidity_Fed_Assets": "Exact duplicate of Liquidity_Fed_Assets_B in USD mn (ratio = 1000).",
    "Liquidity_TGA_B": "Exact duplicate of Liquidity_TGA (identical values).",
    "Liquidity_Margin_Year-Month": "Text label of the FINRA reference month (metadata, not a measurement).",
}

# ---------------------------------------------------------------------------- REGIME PARAMETERS
# All thresholds live here so the methodology section can print them verbatim.
REGIME_PARAMS = dict(
    trend_signal_threshold=0.5,      # |Δ / σ(Δ)| below this => "Stable/Neutral"
    sentiment_fear_pct=25,           # composite percentile < 25 => Fear
    sentiment_greed_pct=75,          # composite percentile > 75 => Greed
    stress_low_pct=50,               # stress percentile < 50 => Low
    stress_high_pct=80,              # stress percentile >= 80 => High
    extreme_high_pct=90,             # >= 90th pct => extreme-high flag
    extreme_low_pct=10,              # <= 10th pct => extreme-low flag
    pc_smoothing_days=10,            # Put/Call 10-trading-day mean used in the composite
    asof_tolerance_daily_days=7,     # as-of alignment tolerance for daily series
    asof_tolerance_weekly_days=12,   # as-of alignment tolerance for weekly series
    transitional_lookback_rows=20,   # trading days used to detect a regime transition
    min_components_composite=2,      # sentiment composite needs >= 2 of 3 components
)
