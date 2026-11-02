#!/usr/bin/env python3
"""Portfolio computation core — no GUI imports, headless-testable.

Ports the math from ~/workspace/portfolio/build_dashboard.py (Google Sheets
version) to local Python. Reads portfolio.csv lots (via positions_from_lots),
fetches prices via yfinance (with a last-known cache fallback), and computes
all views + drift. Legacy holdings.yaml / cost_basis.csv readers are kept
for migration reference only.

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


# ================= unified lots model (portfolio.csv) =================
LOT_FIELDS = ["bank", "account", "account_type", "asset", "shares",
              "cost_per_share", "acquired_date", "sold_date",
              "sale_price_per_share"]
ACCOUNT_TYPES = ["Traditional IRA", "Roth IRA", "Taxable", "HSA", "Cash"]
CASH_ASSET = "CASH_USD"

# Lots needing neither cost nor dates (complete by nature).
RETIREMENT_TYPES = {"Traditional IRA", "Roth IRA", "HSA"}


def _fnum(x):
    try:
        return None if x is None or str(x).strip() == "" else float(x)
    except (ValueError, TypeError):
        return None


def _s(x):
    return "" if x is None else str(x).strip()


def load_portfolio(path):
    """Return [lot] in file order. Lot keys: bank, account, account_type,
    asset, shares, cost, acquired, sold_date, sale_price. Missing file
    (fresh clone — data files are gitignored) yields []."""
    lots = []
    if not os.path.exists(path):
        return lots
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            lots.append({
                "bank": _s(row.get("bank")),
                "account": _s(row.get("account")),
                "account_type": _s(row.get("account_type")),
                "asset": _s(row.get("asset")),
                "shares": _fnum(row.get("shares")),
                "cost": _fnum(row.get("cost_per_share")),
                "acquired": _s(row.get("acquired_date")),
                "sold_date": _s(row.get("sold_date")),
                "sale_price": _fnum(row.get("sale_price_per_share")),
            })
    return lots


def save_portfolio(path, lots):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOT_FIELDS)
        w.writeheader()
        for lot in lots:
            w.writerow({
                "bank": lot.get("bank", ""),
                "account": lot.get("account", ""),
                "account_type": lot.get("account_type", ""),
                "asset": lot.get("asset", ""),
                "shares": "" if lot.get("shares") is None else lot["shares"],
                "cost_per_share": "" if lot.get("cost") is None else lot["cost"],
                "acquired_date": lot.get("acquired", ""),
                "sold_date": lot.get("sold_date", ""),
                "sale_price_per_share": ""
                if lot.get("sale_price") is None else lot["sale_price"],
            })


def lot_status(lot):
    """DERIVED status — never stored. Open iff sold_date is blank."""
    return "Closed" if lot.get("sold_date") else "Open"


def open_lots(lots):
    return [l for l in lots if lot_status(l) == "Open"]


def closed_lots(lots):
    return [l for l in lots if lot_status(l) == "Closed"]


def is_cash_row(lot):
    return lot.get("asset") == CASH_ASSET or lot.get("account_type") == "Cash"


def positions_from_lots(lots):
    """Aggregate OPEN lots by (account, asset) into the position shape the
    existing views consume: [{account, ticker, qty, bucket}]."""
    agg = {}
    order = []
    for lot in open_lots(lots):
        key = (lot["account"], lot["asset"])
        if key not in agg:
            agg[key] = 0.0
            order.append(key)
        agg[key] += lot["shares"] or 0.0
    positions = []
    for account, asset in order:
        positions.append({"account": account, "ticker": asset,
                          "qty": agg[(account, asset)],
                          "bucket": TICKER_BUCKET.get(asset, "Equities")})
    return positions


def cost_map_from_lots(lots):
    """{(account, asset): share-weighted average cost} over open lots that
    carry a cost. Used for the aggregate views; Tax Harvest uses per-lot
    costs directly."""
    tot_shares = {}
    tot_cost = {}
    for lot in open_lots(lots):
        if lot.get("cost") is None or lot.get("shares") is None:
            continue
        key = (lot["account"], lot["asset"])
        tot_shares[key] = tot_shares.get(key, 0.0) + lot["shares"]
        tot_cost[key] = tot_cost.get(key, 0.0) + lot["shares"] * lot["cost"]
    return {k: tot_cost[k] / tot_shares[k]
            for k in tot_cost if tot_shares[k]}


def holding_term(acquired, as_of=None, sold=None):
    """Long if held more than a year, Short otherwise, None if no date.
    `sold` (YYYY-MM-DD) is the end of the holding period when given."""
    if not acquired:
        return None
    try:
        start = datetime.date.fromisoformat(acquired)
        end = datetime.date.fromisoformat(sold) if sold \
            else (as_of or datetime.date.today())
    except ValueError:
        return None
    return "Long" if (end - start).days > 365 else "Short"


def realized_gains_year(lots, year, other=0.0):
    """(total, unknown_count, rows) for lots closed in `year`. Rows with a
    missing cost are EXCLUDED from the total and counted as unknown —
    never invented."""
    total = 0.0
    unknown = 0
    rows = []
    for lot in closed_lots(lots):
        if not lot.get("sold_date", "").startswith(str(year)):
            continue
        if lot.get("cost") is None or lot.get("sale_price") is None \
                or lot.get("shares") is None:
            unknown += 1
            gain = None
        else:
            gain = (lot["sale_price"] - lot["cost"]) * lot["shares"]
            total += gain
        rows.append({"account": lot["account"], "asset": lot["asset"],
                     "shares": lot["shares"], "cost": lot["cost"],
                     "sale_price": lot["sale_price"],
                     "sold_date": lot["sold_date"], "gain": gain,
                     "term": holding_term(lot["acquired"],
                                          sold=lot["sold_date"])})
    return total + (other or 0.0), unknown, rows


def coverage(lots):
    """Coverage roll-ups. Cash rows need nothing, so they are excluded
    from the cost/date denominators."""
    banks = {}
    for lot in open_lots(lots):
        cash = is_cash_row(lot)
        needs = not cash
        pos = {"asset": lot["asset"],
               "shares_ok": lot.get("shares") is not None,
               "cost_ok": (not needs) or lot.get("cost") is not None,
               "acq_ok": (not needs) or bool(lot.get("acquired"))}
        bank = banks.setdefault(lot["bank"] or "?", {"accounts": {}})
        acct = bank["accounts"].setdefault(
            lot["account"], {"type": lot.get("account_type", ""),
                             "positions": []})
        acct["positions"].append(pos)
    total = {"holdings_ok": 0, "holdings_n": 0, "cost_ok": 0, "cost_n": 0,
             "acq_ok": 0, "acq_n": 0, "taxable_n": 0, "retire_n": 0}
    for bank in banks.values():
        for name, acct in bank["accounts"].items():
            npos = len(acct["positions"])
            acct["summary"] = {
                "cost": "%d of %d cost" % (
                    sum(p["cost_ok"] for p in acct["positions"]), npos),
                "dates": "%d of %d dates" % (
                    sum(p["acq_ok"] for p in acct["positions"]), npos)}
            if acct["type"] == "Taxable":
                acct["flag"] = "REQUIRED"
            elif acct["type"] in RETIREMENT_TYPES:
                acct["flag"] = "OPTIONAL"
            else:
                acct["flag"] = "COMPLETE"
            for p in acct["positions"]:
                if acct["type"] != "Cash":
                    total["holdings_ok"] += p["shares_ok"]
                    total["holdings_n"] += 1
                if not _is_cash_pos(acct, p):
                    total["cost_n"] += 1
                    total["cost_ok"] += p["cost_ok"]
                    total["acq_n"] += 1
                    total["acq_ok"] += p["acq_ok"]
                    if acct["type"] == "Taxable":
                        total["taxable_n"] += 1
                    elif acct["type"] in RETIREMENT_TYPES:
                        total["retire_n"] += 1
    return {"banks": banks, "total": total}


def _is_cash_pos(acct, pos):
    return pos["asset"] == CASH_ASSET or acct["type"] == "Cash"





def validate_lot_rows(rows, existing=None, today=None):
    """Validate uploaded template rows (raw CSV dicts). Returns [errors];
    empty means safe to merge. Checks `existing` lots for type conflicts
    but never mutates anything."""
    today = today or datetime.date.today()
    errors = []
    known = set(LOT_FIELDS)
    if rows and set(rows[0].keys()) - known:
        errors.append("unknown columns: %s"
                      % sorted(set(rows[0].keys()) - known))
    types = {}
    for lino, r in enumerate(rows, start=2):
        acct = _s(r.get("account"))
        if not acct or not _s(r.get("asset")):
            errors.append("line %d: account and asset are required" % lino)
        shares = _fnum(r.get("shares"))
        if shares is None or shares <= 0:
            errors.append("line %d: shares must be a positive number" % lino)
        if _s(r.get("cost_per_share")) and _fnum(r.get("cost_per_share")) is None:
            errors.append("line %d: cost_per_share must be numeric" % lino)
        for field in ("acquired_date", "sold_date"):
            if _s(r.get(field)):
                try:
                    datetime.date.fromisoformat(_s(r.get(field)))
                except ValueError:
                    errors.append("line %d: %s must be YYYY-MM-DD" % (lino, field))
        if _s(r.get("sale_price_per_share")) and \
                _fnum(r.get("sale_price_per_share")) is None:
            errors.append("line %d: sale_price_per_share must be numeric"
                          % lino)
        if bool(_s(r.get("sold_date"))) != bool(_s(r.get("sale_price_per_share"))):
            errors.append("line %d: sold_date and sale_price_per_share go "
                          "together" % lino)
        if _s(r.get("acquired_date")) and _s(r.get("sold_date")) and \
                _s(r.get("sold_date")) < _s(r.get("acquired_date")):
            errors.append("line %d: sold_date precedes acquired_date" % lino)
        if _s(r.get("acquired_date")) > today.isoformat():
            errors.append("line %d: acquired_date is in the future" % lino)
        atype = _s(r.get("account_type"))
        if atype and atype not in ACCOUNT_TYPES:
            errors.append("line %d: account_type must be one of %s"
                          % (lino, ", ".join(ACCOUNT_TYPES)))
        if acct and atype:
            types.setdefault(acct, set()).add(atype)
    for acct, ts in types.items():
        if len(ts) > 1:
            errors.append("account %r has conflicting types in upload: %s"
                          % (acct, sorted(ts)))
    seen = {}
    for lino, r in enumerate(rows, start=2):
        try:
            key = lot_key_of(r.get("account"), r.get("asset"),
                             r.get("acquired_date"), r.get("cost_per_share"))
        except Exception:  # noqa: BLE001 - malformed cells already errored
            continue
        # Closed rows are history and may share a key with their open
        # residual (a normal post-split state); only two OPEN rows sharing
        # a key are ambiguous and must be combined.
        if _s(r.get("sold_date")):
            continue
        if key in seen:
            errors.append("line %d duplicates line %d (same account, asset, "
                          "acquired date and cost) — combine them first"
                          % (lino, seen[key]))
        else:
            seen[key] = lino
    if existing:
        known_types = {}
        for lot in existing:
            if lot.get("account_type"):
                known_types.setdefault(lot["account"], set()).add(
                    lot["account_type"])
        for acct, ts in types.items():
            if acct in known_types and not ts <= known_types[acct]:
                errors.append("account %r type %s conflicts with stored %s"
                              % (acct, sorted(ts),
                                 sorted(known_types[acct])))
    return errors


def lot_key_of(account, asset, acquired, cost):
    """Lot identity: (account, asset, acquired_date, cost_per_share).
    Cost normalizes so 10 and 10.0 are the same key."""
    try:
        cost = None if cost is None or str(cost).strip() == "" \
            else float(cost)
    except (ValueError, TypeError):
        cost = str(cost)
    return (_s(account), _s(asset), _s(acquired), cost)


def lot_key(lot):
    return lot_key_of(lot.get("account"), lot.get("asset"),
                      lot.get("acquired"), lot.get("cost"))


def row_to_lot(r):
    return {
        "bank": _s(r.get("bank")),
        "account": _s(r.get("account")),
        "account_type": _s(r.get("account_type")),
        "asset": _s(r.get("asset")),
        "shares": _fnum(r.get("shares")),
        "cost": _fnum(r.get("cost_per_share")),
        "acquired": _s(r.get("acquired_date")),
        "sold_date": _s(r.get("sold_date")),
        "sale_price": _fnum(r.get("sale_price_per_share")),
    }


def merge_lots(existing, uploaded_rows):
    """Lot-key UPSERT into a new list; inputs untouched. A matching
    (account, asset, acquired_date, cost_per_share) key replaces the
    mutable fields (shares, sold_date, sale_price, bank, account_type);
    anything else inserts. NEVER deletes rows — deletions happen only via
    the Delete-lot action. Returns (merged, inserted_keys)."""
    merged = [dict(l) for l in existing]
    index = {}
    for l in merged:
        index[lot_key(l)] = l
    inserted = []
    for r in uploaded_rows:
        new = row_to_lot(r)
        key = lot_key(new)
        if key in index:
            old = index[key]
            old.update({k: new[k] for k in
                        ("bank", "account_type", "shares", "sold_date",
                         "sale_price")})
        else:
            merged.append(new)
            index[key] = new
            inserted.append(key)
    return merged, inserted


def drawdown_dated(merged, inserted_keys):
    """Draw newly attributed dated lots out of the dateless (unattributed)
    balance for the same (account, asset): dateless open rows are reduced
    in file order and zeroed ones dropped, keeping a positive residual row.
    Returns [errors] (dated shares exceeding the balance); mutates `merged`
    only on the success path — callers must discard it when errors occur.

    `inserted_keys` are lot keys absent before this upload, so a
    re-uploaded dated lot never draws twice."""
    need = {}
    for key in inserted_keys:
        acct, asset, acquired, _cost = key
        if not acquired or asset == CASH_ASSET:
            continue
        lot = next((l for l in merged if lot_key(l) == key), None)
        if lot is not None and lot_status(lot) == "Open":
            need[(acct, asset)] = need.get((acct, asset), 0.0) + \
                (lot["shares"] or 0.0)
    return drawdown_amounts(merged, need, exclude_keys=set(inserted_keys))


def dated_totals(lots):
    """{(account, asset): dated non-cash shares, open AND closed}.
    Closing/reopening a dated row must not look like attribution growth."""
    totals = {}
    for lot in lots:
        if lot.get("acquired") and lot.get("asset") != CASH_ASSET:
            key = (lot.get("account"), lot.get("asset"))
            totals[key] = totals.get(key, 0.0) + (lot["shares"] or 0.0)
    return totals


def undated_totals(lots):
    """{(account, asset): dateless non-cash shares, open AND closed} —
    the unattributed balance. The drawdown pool itself stays open-only
    (sold unattributed shares cannot fund new attribution)."""
    totals = {}
    for lot in lots:
        if not lot.get("acquired") and lot.get("asset") != CASH_ASSET \
                and lot.get("account_type") != "Cash":
            key = (lot.get("account"), lot.get("asset"))
            totals[key] = totals.get(key, 0.0) + (lot["shares"] or 0.0)
    return totals


def drawdown_amounts(merged, needs, exclude_keys=()):
    """Draw explicit {((account, asset)): shares} needs out of the dateless
    balance, as drawdown_dated. Used by grid saves, where a row gaining a
    date converts its own shares (net-change need) instead of drawing."""
    errors = []
    excluded = set(exclude_keys)
    for (acct, asset), qty in needs.items():
        if qty <= 1e-9:
            continue
        pre = [l for l in merged if l.get("account") == acct
               and l.get("asset") == asset and lot_key(l) not in excluded]
        if not pre:
            continue  # genuinely new position — no balance to draw from
        pool = [l for l in merged
                if lot_status(l) == "Open" and not l.get("acquired")
                and l.get("asset") == asset and l.get("account") == acct
                and l.get("account_type") != "Cash"
                and lot_key(l) not in excluded]
        balance = sum(l["shares"] or 0.0 for l in pool)
        if qty - balance > 1e-9:
            errors.append(
                "%s / %s: dated lots total %s shares but the unattributed "
                "(dateless) balance is only %s — excess shares rejected" % (
                    acct, asset, _fmt_shares(qty), _fmt_shares(balance)))
            continue
        left = qty
        for l in pool:
            if left <= 1e-9:
                break
            take = min(l["shares"] or 0.0, left)
            l["shares"] = (l["shares"] or 0.0) - take
            left -= take
        for l in [l for l in pool if (l["shares"] or 0.0) <= 1e-9]:
            merged.remove(l)
    return errors


def _fmt_shares(x):
    return ("%g" % x)


def merge_upload(existing, uploaded_rows):
    """Atomic upload merge: lot-key upsert + dateless drawdown on a copy.
    Returns (merged_or_None, inserted, errors) — on errors NOTHING commits,
    so callers assign only when errors is empty."""
    merged, inserted = merge_lots(existing, uploaded_rows)
    errors = drawdown_dated(merged, inserted)
    if errors:
        return None, [], errors
    return merged, inserted, []


def split_for_sale(lot, qty, sold_date, sale_price, cost=None):
    """Auto-split an open lot for a partial sale: returns (closed_row,
    open_row). Full-quantity sales just fill the dates (see Close)."""
    if cost is not None:
        lot = dict(lot, cost=cost)
    closed = dict(lot, shares=qty, sold_date=sold_date, sale_price=sale_price)
    open_row = dict(lot, shares=(lot["shares"] or 0.0) - qty,
                    sold_date="", sale_price=None)
    return closed, open_row


def account_values(lots, prices):
    """{(bank, account): liquid value} over OPEN lots (CASH_USD at $1).
    Missing prices are skipped (never crash on price failure)."""
    vals = {}
    for lot in open_lots(lots):
        price = 1.0 if lot.get("asset") == CASH_ASSET \
            else prices.get(lot.get("asset"))
        if price is None or lot.get("shares") is None:
            continue
        key = (lot.get("bank") or "?", lot.get("account"))
        vals[key] = vals.get(key, 0.0) + lot["shares"] * price
    return vals


def holdings_by_asset(lots, prices, home_value, home_cost=None):
    """One row per asset aggregated across accounts (open lots only;
    CASH_USD excluded — cash lives in Liquidity). Avg cost covers KNOWN-cost
    lots only; unknown-cost shares are counted in `missing` and never
    averaged in. Gain is computed on the known portion only. Home is one
    more row (cost = purchase price if known, else value only, no gain).
    Returns ([rows], total_value) sorted by value desc; each row carries
    per-account lot detail for expansion."""
    agg = {}
    for lot in open_lots(lots):
        if lot.get("asset") == CASH_ASSET:
            continue
        a = agg.setdefault(lot["asset"], {"shares": 0.0, "known_sh": 0.0,
                                          "known_cost": 0.0, "by_acct": {}})
        sh = lot.get("shares") or 0.0
        a["shares"] += sh
        if lot.get("cost") is not None:
            a["known_sh"] += sh
            a["known_cost"] += sh * lot["cost"]
        a["by_acct"].setdefault(lot.get("account"), []).append(lot)
    rows = []
    for asset, a in agg.items():
        price = prices.get(asset)
        value = None if price is None else a["shares"] * price
        avg = a["known_cost"] / a["known_sh"] if a["known_sh"] else None
        if price is not None and avg is not None:
            gain = a["known_sh"] * (price - avg)
            gain_pct = gain / a["known_cost"] if a["known_cost"] else None
        else:
            gain, gain_pct = None, None
        rows.append({"asset": asset, "shares": a["shares"],
                     "missing": a["shares"] - a["known_sh"],
                     "avg_cost": avg, "price": price, "value": value,
                     "gain": gain, "gain_pct": gain_pct,
                     "by_acct": a["by_acct"]})
    rows.append({"asset": "Home (real estate)", "shares": 1.0, "missing": 0.0,
                 "avg_cost": home_cost, "price": home_value,
                 "value": home_value,
                 "gain": None if home_cost is None
                 else home_value - home_cost,
                 "gain_pct": None if not home_cost
                 else (home_value - home_cost) / home_cost,
                 "by_acct": {}})
    rows.sort(key=lambda r: (r["value"] is None, -(r["value"] or 0)))
    total = sum(r["value"] for r in rows if r["value"] is not None)
    return rows, total


def fifo_order(lots):
    """Open lots oldest-first by acquired_date; dateless lots sort last
    (stable otherwise)."""
    return sorted(open_lots(lots),
                  key=lambda l: (not l.get("acquired"), l.get("acquired")))


def fifo_sell(lots, account, asset, qty, sold_date, sale_price, cost=None):
    """Sell `qty` shares of one position FIFO: oldest lots first, dateless
    last, auto-spanning via split_for_sale. Creates one closed row per lot
    consumed, each carrying the sale date and price. Lots missing a cost
    take `cost` when given, else stay unknown (never invented).
    Returns (new_lots, error_or_None) — new_lots is a copy; on error the
    caller's list is untouched."""
    if qty is None or qty <= 0:
        return lots, "quantity must be positive"
    cands = [l for l in fifo_order(lots)
             if l.get("account") == account and l.get("asset") == asset
             and not is_cash_row(l)]
    held = sum(l["shares"] or 0.0 for l in cands)
    if qty - held > 1e-9:
        return lots, "only %s shares held, cannot sell %s" % (
            _fmt_shares(held), _fmt_shares(qty))
    new_lots = [dict(l) for l in lots]
    by_id = {id(l): n for l, n in zip(lots, new_lots)}
    left = qty
    for cand in cands:
        if left <= 1e-9:
            break
        mine = by_id[id(cand)]
        take = min(mine["shares"] or 0.0, left)
        if take < (mine["shares"] or 0.0) - 1e-9:
            closed, opened = split_for_sale(mine, take, sold_date,
                                            sale_price, cost)
            at = new_lots.index(mine)
            new_lots[at] = closed
            new_lots.insert(at + 1, opened)
        else:
            mine["sold_date"] = sold_date
            mine["sale_price"] = sale_price
            if cost is not None and mine.get("cost") is None:
                mine["cost"] = cost
        left -= take
    return new_lots, None


# ================= profile (profile.json) =================
PROFILE_DEFAULTS = {
    "date_of_birth": "1968-08",
    "ss_owner_monthly": 1812,
    "ss_spouse_monthly": 700,
    "other_realized_gains_current_year": 3219.16,
    "other_realized_gains_note":
        "Schwab Living Trust 2026 YTD (pre-app history)",
    # Sheet-ported annual spending figures (user-confirmed constants, like
    # the TLH cap below); after-65 all-in adds Social Security live.
    "spending_before65_annual": 135545,
    "spending_after65_base_annual": 111900,
    # Home purchase price (optional — Holdings shows value-only without it).
    "home_purchase_price": "",
}


def load_profile(path):
    prof = dict(PROFILE_DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path) as f:
                prof.update(json.load(f))
        except (ValueError, OSError):
            pass
    return prof


def save_profile(path, prof):
    with open(path, "w") as f:
        json.dump(prof, f, indent=1, sort_keys=True)


def spending_capacity(prof, today=None):
    """Live spending figures from the profile. Base annuals are the
    sheet-ported constants; after-65 all-in adds both SS checks monthly."""
    today = today or datetime.date.today()
    dob = str(prof.get("date_of_birth", ""))[:7]
    try:
        y, m = int(dob[:4]), int(dob[5:7])
        turns65 = datetime.date(y + 65, m, 1).strftime("%b %Y")
        age = today.year - y - ((today.month, today.day) < (m, 1))
        months_left = max((y + 65 - today.year) * 12 + (m - today.month), 0)
    except (ValueError, TypeError):
        turns65, age, months_left = "--", None, None
    before = float(prof.get("spending_before65_annual", 0) or 0)
    base = float(prof.get("spending_after65_base_annual", 0) or 0)
    ss = 12 * (float(prof.get("ss_owner_monthly", 0) or 0)
               + float(prof.get("ss_spouse_monthly", 0) or 0))
    return {"before65": before, "after65_base": base,
            "after65_allin": base + ss, "turns65": turns65, "age": age,
            "months_to_65": months_left}
