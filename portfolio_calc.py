#!/usr/bin/env python3
"""Portfolio computation core — no GUI imports, headless-testable.

Ports the math from ~/workspace/portfolio/build_dashboard.py (Google Sheets
version) to local Python. Reads holdings.yaml, fetches prices via yfinance
(with a last-known cache fallback), and computes all 6 views + drift.

NEVER executes trades, NEVER touches Google Sheets, NEVER asks for passwords.
"""
import csv
import datetime
import json
import os

# ---- Constants (mirroring the sheet) ----
ACCOUNTS = ["Wells IRA", "Wells Savings", "Chase IRA (Ashu)", "chase Savings",
            "Chase Brokerage (Lovey)", "Schwab Roth", "Schwab living Trust",
            "Schwab Ashu IRA", "Vanguard Brokerage", "Vanguard IRA",
            "Health Equity", "coinbase", "cashApp"]
LT65 = {"Wells Savings", "chase Savings", "Chase Brokerage (Lovey)",
        "Schwab living Trust", "Vanguard Brokerage", "Health Equity",
        "coinbase", "cashApp"}

BUCKETS = ["BTC & related", "Gold & silver", "Equities", "Cash & cash-like",
           "Real Estate (home, Zillow)"]
TARGETS = [0.15, 0.15, 0.35, 0.15, 0.20]

# Ticker -> bucket. Anything not listed here is Equities (sheet's "E" code).
TICKER_BUCKET = {
    "BTC": "BTC & related", "ETH": "BTC & related", "ARKB": "BTC & related",
    "IBIT": "BTC & related", "MSTR": "BTC & related", "BMNR": "BTC & related",
    "GLD": "Gold & silver", "SLV": "Gold & silver",
    "STRC": "Cash & cash-like", "CASH_USD": "Cash & cash-like",
}
# Ticker -> Yahoo symbol (everything else maps to itself).
YAHOO = {"BTC": "BTC-USD", "ETH": "ETH-USD"}

# Calendar-year drift baseline (Dec 30, 2025 snapshot; rolls each January —
# update these two numbers from the new Dec snapshot tab each year).
BASELINE_LIQUID = 3595000
BASELINE_HOME = 931000
BASELINE_TOTAL = BASELINE_LIQUID + BASELINE_HOME
JAN1_PRICES = {"BTC": 87413, "GLD": 398.28, "VTI": 336.31, "MSTR": 157}

HOME_DEFAULT = 853000

# Tax-loss harvesting budget (user-confirmed, Schwab Living Trust ...035).
TLH_CAP = 15000
TLH_GAINS_YTD = 3219.16
TLH_LOSSES_YTD = 0.0


# ================= holdings =================
def _strip_comment(line):
    """Remove a ' #' comment, respecting double-quoted strings."""
    in_q = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_q = not in_q
        elif ch == "#" and not in_q and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line


def _manual_parse_holdings(path):
    """Minimal parser for this project's holdings.yaml shape only.

    Understands:
        accounts:
          "Name":
            TICKER: qty
        savings:
          "Name": value
    Stops at the notes: section. Ignores comments/blank lines.
    """
    positions = []
    section = None
    account = None
    with open(path) as f:
        for raw in f:
            line = _strip_comment(raw.rstrip("\n"))
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "accounts:":
                section, account = "accounts", None
                continue
            if stripped == "savings:":
                section, account = "savings", None
                continue
            if stripped == "notes:":
                break
            indent = len(line) - len(line.lstrip(" "))
            if section == "accounts" and indent == 2 and stripped.endswith(":"):
                account = stripped[:-1].strip().strip('"')
                continue
            if section == "accounts" and indent == 4 and account:
                t, _, q = stripped.partition(":")
                positions.append({"account": account, "ticker": t.strip(),
                                  "qty": float(q.strip())})
                continue
            if section == "savings" and indent == 2:
                name, _, val = stripped.partition(":")
                positions.append({"account": name.strip().strip('"'),
                                  "ticker": "CASH_USD",
                                  "qty": float(val.strip())})
    return positions


def load_holdings(path):
    """Return [{account, ticker, qty, bucket}] in file order."""
    try:
        import yaml  # type: ignore
        with open(path) as f:
            doc = yaml.safe_load(f)
        positions = []
        for acct, tickers in (doc.get("accounts") or {}).items():
            for t, q in tickers.items():
                positions.append({"account": acct, "ticker": t,
                                  "qty": float(q)})
        for acct, val in (doc.get("savings") or {}).items():
            positions.append({"account": acct, "ticker": "CASH_USD",
                              "qty": float(val)})
    except ImportError:
        positions = _manual_parse_holdings(path)
    for p in positions:
        p["bucket"] = TICKER_BUCKET.get(p["ticker"], "Equities")
    return positions


def load_cost_basis(path):
    """Return {(account, ticker): cost_per_share}. Blank/absent = no basis."""
    basis = {}
    if not os.path.exists(path):
        return basis
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                cost = (row.get("cost_per_share") or "").strip()
                if cost:
                    basis[(row["account"].strip(), row["ticker"].strip())] = float(cost)
            except (KeyError, ValueError):
                continue
    return basis


# ================= prices =================
def load_price_cache(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            return {k: v for k, v in d.items()
                    if isinstance(v, (int, float))}
        except (ValueError, OSError):
            pass
    return {}


def save_price_cache(path, prices, as_of):
    d = dict(prices)
    d["as_of"] = as_of
    with open(path, "w") as f:
        json.dump(d, f, indent=1, sort_keys=True)


def fetch_prices(tickers, cache_path):
    """Fetch last closes via yfinance, one ticker at a time.

    Batch yf.download is flaky (timeouts); per-ticker history() is reliable.
    Returns (prices, errors, used_cache_any). Failures fall back to the
    last-known cache for that ticker; a ticker with neither is None.
    """
    cache = load_price_cache(cache_path)
    prices = {}
    errors = []
    try:
        import yfinance as yf
    except ImportError:
        yf = None
        errors.append("yfinance not installed — using last-known prices")
    if yf is not None:
        from concurrent.futures import ThreadPoolExecutor

        def one(t):
            try:
                h = yf.Ticker(YAHOO.get(t, t)).history(period="5d")
                if len(h):
                    return t, round(float(h["Close"].iloc[-1]), 2)
            except Exception as e:  # noqa: BLE001 - per-ticker resilience
                return t, ("ERR:%s" % type(e).__name__)
            return t, None

        with ThreadPoolExecutor(max_workers=8) as ex:
            for t, v in ex.map(one, tickers):
                if isinstance(v, (int, float)):
                    prices[t] = v
                else:
                    if v is not None and v.startswith("ERR"):
                        errors.append("%s: %s" % (t, v[4:]))
                    if t in cache:
                        prices[t] = cache[t]
    else:
        prices = dict(cache)
    # Merge fresh prices into the cache for next time.
    fresh = {t: v for t, v in prices.items() if isinstance(v, (int, float))}
    if fresh:
        merged = dict(cache)
        merged.update(fresh)
        save_price_cache(cache_path, merged,
                         datetime.date.today().isoformat())
    used_cache = any(t not in fresh and t in prices for t in tickers)
    return prices, errors, used_cache


# ================= views =================
def fmt_usd(x):
    if x is None:
        return "--"
    sign = "-" if x < 0 else ""
    return "%s$%s" % (sign, f"{abs(x):,.0f}")


def fmt_pct(x):
    if x is None:
        return "--"
    return "%.1f%%" % (x * 100)


def compute(positions, prices, home_value, cost_basis=None):
    """Compute all views. prices: {ticker: price}; missing -> value None."""
    cost_basis = cost_basis or {}
    # Position values.
    for p in positions:
        price = prices.get(p["ticker"])
        if p["ticker"] == "CASH_USD":
            price = 1.0
        p["price"] = price
        p["value"] = None if price is None else p["qty"] * price

    def bsum(bucket, account=None):
        return sum(p["value"] for p in positions
                   if p["bucket"] == bucket and p["value"] is not None
                   and (account is None or p["account"] == account))

    liquid = sum(p["value"] for p in positions if p["value"] is not None)
    tnw = liquid + home_value

    # View 1 — Accounts.
    v1 = []
    for acct in ACCOUNTS:
        vals = {b: bsum(b, acct) for b in BUCKETS[:4]}
        total = sum(vals.values())
        v1.append({"account": acct, **vals, "re": 0.0, "total": total,
                   "pct": (total / tnw) if tnw else 0.0})
    v1.append({"account": "Real Estate (home)", "BTC & related": 0.0,
               "Gold & silver": 0.0, "Equities": 0.0, "Cash & cash-like": 0.0,
               "re": home_value, "total": home_value,
               "pct": (home_value / tnw) if tnw else 0.0})
    totals = {b: sum(r[b] for r in v1[:-1]) for b in BUCKETS[:4]}
    totals["re"] = home_value
    total_all = sum(totals.values())
    v1_total = {"account": "TOTAL", **totals, "total": total_all, "pct": 1.0}
    mix = {b: (totals[b] / total_all) if total_all else 0.0
           for b in BUCKETS[:4]}
    mix["re"] = (home_value / total_all) if total_all else 0.0

    # View 2 — Liquidity.
    lt = sum(r["total"] for r in v1 if r["account"] in LT65)
    gt = sum(r["total"] for r in v1
             if r["account"] not in LT65
             and r["account"] not in ("Real Estate (home)",))
    v2 = {"lt": lt, "gt": gt, "re": home_value, "tnw": tnw,
          "lt_pct": lt / tnw if tnw else 0.0,
          "gt_pct": gt / tnw if tnw else 0.0,
          "re_pct": home_value / tnw if tnw else 0.0}

    # View 3 — Diversification vs standard.
    v3 = []
    for b, tgt in zip(BUCKETS, TARGETS):
        actual = bsum(b) if b != BUCKETS[4] else home_value
        actual_pct = actual / tnw if tnw else 0.0
        v3.append({"bucket": b, "target_pct": tgt,
                   "target_dollar": tgt * tnw, "actual": actual,
                   "actual_pct": actual_pct,
                   "deviation_pp": (actual_pct - tgt) * 100,
                   "rebalance": tgt * tnw - actual})

    # View 4 — Rebalance plan (display only; mirrors the sheet's sizing).
    meta = prices.get("META")
    vti = prices.get("VTI")
    gld = prices.get("GLD")
    ibit = prices.get("IBIT")
    strc = prices.get("STRC")

    def shares(anchor, price):
        return None if price is None else round(anchor / price)

    t1_sh = shares(267000, meta)
    t1_proc = None if (t1_sh is None or meta is None) else t1_sh * meta
    t1_buy = None if (t1_proc is None or ibit is None) else round(t1_proc / ibit)
    t2_sh = shares(282000, vti)
    t2_proc = None if (t2_sh is None or vti is None) else t2_sh * vti
    t3_sh = shares(115000, gld)
    t3_proc = None if (t3_sh is None or gld is None) else t3_sh * gld
    cash_before = bsum("Cash & cash-like")
    cash_after = cash_before + (t2_proc or 0) + (t3_proc or 0)
    strc_topup = None
    strc_sh = None
    if strc is not None:
        strc_topup = round(0.2 * cash_after - 270 * strc)
        strc_sh = round(strc_topup / strc)
    btc_b, gold_b, eq_b = bsum("BTC & related"), bsum("Gold & silver"), bsum("Equities")
    after = {
        "BTC & related": btc_b + (t1_proc or 0),
        "Gold & silver": gold_b - (t3_proc or 0),
        "Equities": eq_b - (t1_proc or 0) - (t2_proc or 0),
        "Cash & cash-like": cash_after,
        "Real Estate (home, Zillow)": home_value,
    }
    v4 = {
        "trades": [
            {"n": 1, "sell": "META", "sell_sh": t1_sh, "proceeds": t1_proc,
             "buy": "IBIT", "buy_sh": t1_buy},
            {"n": 2, "sell": "VTI", "sell_sh": t2_sh, "proceeds": t2_proc,
             "buy": "Cash (sweep)", "buy_sh": None},
            {"n": 3, "sell": "GLD", "sell_sh": t3_sh, "proceeds": t3_proc,
             "buy": "Cash (sweep)", "buy_sh": None},
            {"n": 4, "sell": "Cash (from sweeps)", "sell_sh": None,
             "proceeds": strc_topup, "buy": "STRC", "buy_sh": strc_sh},
        ],
        "before": {"BTC & related": btc_b, "Gold & silver": gold_b,
                   "Equities": eq_b, "Cash & cash-like": cash_before,
                   "Real Estate (home, Zillow)": home_value},
        "after": after,
        "after_total": sum(after.values()),
    }

    # View 5 — Tax-loss harvesting.
    v5 = []
    for p in positions:
        cost = cost_basis.get((p["account"], p["ticker"]))
        if cost is not None and p["price"] is not None:
            pnl = p["qty"] * (p["price"] - cost)
        else:
            pnl = None
        v5.append({"ticker": p["ticker"], "account": p["account"],
                   "qty": p["qty"], "cost": cost, "price": p["price"],
                   "value": p["value"], "pnl": pnl, "bucket": p["bucket"]})
    losers = sorted([r for r in v5 if r["pnl"] is not None and r["pnl"] < 0],
                    key=lambda r: r["pnl"])
    for i, r in enumerate(losers, start=1):
        r["rank"] = i
    for r in v5:
        r.setdefault("rank", None)
    net = TLH_GAINS_YTD + TLH_LOSSES_YTD
    budget = {"cap": TLH_CAP, "gains": TLH_GAINS_YTD,
              "losses": TLH_LOSSES_YTD, "net": net, "left": TLH_CAP - net}

    # Drift — calendar-year baseline (sheet's drift block).
    today = datetime.date.today()
    jan1 = datetime.date(today.year, 1, 1)
    days = max((today - jan1).days, 0)

    def ret(now, base):
        return None if (now is None or base in (None, 0)) else (now - base) / base

    rets = {
        "BTC": ret(prices.get("BTC"), JAN1_PRICES["BTC"]),
        "GLD": ret(prices.get("GLD"), JAN1_PRICES["GLD"]),
        "VTI": ret(prices.get("VTI"), JAN1_PRICES["VTI"]),
        "MSTR": ret(prices.get("MSTR"), JAN1_PRICES["MSTR"]),
        "RE": ret(home_value, BASELINE_HOME),
    }
    if all(v is not None for v in rets.values()):
        std_ytd = (0.15 * (0.6 * rets["BTC"] + 0.4 * rets["MSTR"])
                   + 0.15 * rets["GLD"] + 0.35 * rets["VTI"]
                   + 0.15 * (0.05 * days / 365) + 0.20 * rets["RE"])
    else:
        std_ytd = None
    actual_ytd = (tnw - BASELINE_TOTAL) / BASELINE_TOTAL if tnw else None
    drift_pp = None if (actual_ytd is None or std_ytd is None) \
        else actual_ytd - std_ytd
    drift = {
        "baseline_total": BASELINE_TOTAL, "today_total": tnw,
        "actual_ytd": actual_ytd, "standard_ytd": std_ytd,
        "drift_pp": drift_pp,
        "drift_dollar": None if drift_pp is None else drift_pp * BASELINE_TOTAL,
        "standard_total": None if std_ytd is None
        else BASELINE_TOTAL * (1 + std_ytd),
        "returns": rets, "days": days,
    }
    return {"positions": positions, "liquid": liquid, "tnw": tnw,
            "view1": v1, "view1_total": v1_total, "mix": mix, "view2": v2,
            "view3": v3, "view4": v4, "view5": v5, "budget": budget,
            "drift": drift}


# ================= drift log =================
def load_drift_log(path):
    rows = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "date": row["date"],
                        "liquid": float(row["liquid"]),
                        "home": float(row["home"]),
                        "actual_total": float(row["actual_total"]),
                        "standard_total": float(row["standard_total"]),
                    })
                except (KeyError, ValueError):
                    continue
    rows.sort(key=lambda r: r["date"])
    return rows


def append_close(path, liquid, home, actual_total, standard_total):
    """Upsert today's row (like the sheet's log_daily_close.py)."""
    today = datetime.date.today()
    if today.weekday() >= 5:
        return "weekend — no market close to log"
    rows = load_drift_log(path)
    iso = today.isoformat()
    new = {"date": iso, "liquid": round(liquid), "home": round(home),
           "actual_total": round(actual_total),
           "standard_total": round(standard_total)}
    rows = [r for r in rows if r["date"] != iso] + [new]
    rows.sort(key=lambda r: r["date"])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "liquid", "home",
                                          "actual_total", "standard_total"])
        w.writeheader()
        w.writerows(rows)
    return "logged %s: liquid %s, total %s" % (iso, fmt_usd(liquid),
                                              fmt_usd(actual_total))


# ================= charts =================
def make_allocation_chart(fig, view3):
    """Target vs Actual column chart across the 5 buckets.

    Caller owns the backend: headless runs set MPLBACKEND=Agg before
    importing pyplot; the GUI uses TkAgg via FigureCanvasTkAgg.
    """
    labels = [r["bucket"].replace(" (home, Zillow)", "") for r in view3]
    target = [r["target_pct"] * 100 for r in view3]
    actual = [r["actual_pct"] * 100 for r in view3]
    ax = fig.add_subplot(111)
    x = range(len(labels))
    w = 0.38
    ax.bar([i - w / 2 for i in x], target, w, label="Target %", color="#4285F4")
    ax.bar([i + w / 2 for i in x], actual, w, label="Actual %", color="#EA4335")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("% of total net worth")
    ax.set_title("Target vs actual allocation (total net worth)")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return ax


def make_drift_chart(fig, log_rows):
    """Actual vs Standard daily close — Y axis EXACTLY 2M-5M, ticks every 100K.

    This is the chart the user left Google Sheets for: the old 0-5M axis
    flattened every wiggle into a straight line.
    """
    import matplotlib.dates as mdates
    dates = [datetime.date.fromisoformat(r["date"]) for r in log_rows]
    actual = [r["actual_total"] for r in log_rows]
    standard = [r["standard_total"] for r in log_rows]
    ax = fig.add_subplot(111)
    ax.plot(dates, actual, label="Actual total $", color="#4285F4",
            linewidth=2)
    ax.plot(dates, standard, label="Standard total $", color="#EA4335",
            linewidth=2)
    ax.set_ylim(2000000, 5000000)
    ax.set_yticks(range(2000000, 5000001, 100000))
    ax.set_yticklabels(["$%.1fM" % (v / 1e6)
                        for v in range(2000000, 5000001, 100000)],
                       fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d, %Y"))
    fig.autofmt_xdate(rotation=30)
    ax.set_title("Actual vs Standard -- daily close (total net worth)")
    ax.legend(loc="lower left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return ax
