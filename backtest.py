import pandas as pd
import os
import json
import arrow
from tqdm import tqdm
from collections import Counter
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi

load_dotenv()
alpaca = tradeapi.REST()
tradable_assets = [
    asset.symbol for asset in alpaca.list_assets(status="active") if asset.tradable
]


if not os.path.exists("cache"):
    os.makedirs("cache")

# stock price cache
if not os.path.exists("cache/prices.json"):
    price_cache = {}
else:
    with open("cache/prices.json") as f:
        price_cache = json.load(f)


def clean_df(df, use_cache=True):
    """
    Convert time and expiry from various formats and convert premium to number

    df prior to cleaning:
    =====================
    Date                            Time Ticker    Expiry Strike   C/P    Spot   Qty     Price   Type Volume       OI   Premium   Sector Unusual
    0  6/13/17  2017-06-13T22:58:24.752Z   NTNX  10/17(M)     20   Put   17.97   701  4.000000  SWEEP    701   3689.0  $280,400  ETF/ETN    True
    1  6/13/17  2017-06-13T22:54:53.948Z     KO  06/30/17     45  Call   45.01   769  0.430000  SWEEP   1228    832.0   $33,067  ETF/ETN   False
    2  6/13/17  2017-06-13T22:53:32.255Z     MU  06/16/17     32  Call   31.49   912  0.357774  SWEEP  17065  14769.0   $32,628  ETF/ETN   False
    3  6/13/17  2017-06-13T22:51:41.968Z     PE  07/17(M)     30  Call   28.61  2000  0.698850  SWEEP   2259   3054.0  $139,769  ETF/ETN   False
    4  6/13/17  2017-06-13T22:49:01.261Z    SPY  07/07/17  244.5  Call  244.45   908  1.270000  SWEEP   1932   1684.0  $115,316  ETF/ETN   False
    """
    if use_cache and os.path.exists("cache/hist_options.pkl"):
        return pd.read_pickle("cache/hist_options.pkl")

    print("cleaning and converting df")
    dates, expiries, rows, premium = [], [], [], []
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        try:
            # time had date in 2017 pulls
            if row.Time[:4] == "2017":
                date = arrow.get(arrow.get(row.Time))
            # combine date and time
            else:
                s = [int(x) for x in row.Date.split("/")]
                date = f"20{s[2]}-{s[0]:02}-{s[1]:02}"
                date = arrow.get(date)
                date = f"{date.format('YYYY-MM-DD')}T{row.Time}-05:00"
                date = arrow.get(date)

            # only month provided
            if row.Expiry[-3:] == "(M)":
                expiry = arrow.get(row.Expiry[:5], "MM/YY")
            elif row.Expiry[2] == "/":
                s = [int(x) for x in row.Date.split("/")]
                ds = f"20{s[2]}-{s[0]:02}-{s[1]:02}"
                expiry = arrow.get(ds)
            else:
                expiry = arrow.get(row.Expiry)

            premium.append(int(row.Premium[1:].replace(",", "")))
            dates.append(date)
            expiries.append(expiry)
            rows.append(row)
        except:
            pass

    df = pd.DataFrame(rows)
    df["Time"] = dates
    df["Expiry"] = expiries
    df["Premium"] = premium

    # sort by time
    index = df.index
    df = df.sort_values("Time")
    df.index = index

    df.to_pickle("cache/hist_options.pkl")
    return df


def get_price(symbol, time):
    return get_prices([symbol], time)[symbol]


def get_prices(symbols, time):
    day = time.format("YYYY-MM-DD")

    # if any prices are missing from the cache
    if any([f"{symbol}{day}" not in price_cache for symbol in symbols]):
        symbols.append("SPY")
        start = time.shift(days=-1).isoformat()
        end = time.shift(days=1).isoformat()
        quotes = alpaca.get_barset(symbols, "1D", start=start, end=end)

        # cache values
        values = {f"{symbol}{day}": quotes[symbol][-1].c for symbol in symbols}
        price_cache.update(values)
        with open("cache/prices.json", "w") as f:
            json.dump(price_cache, f, indent=4)

        return {symbol: quotes[symbol][-1].c for symbol in symbols}

    # fetch from cache
    return {symbol: price_cache[f"{symbol}{day}"] for symbol in symbols}


def holdings_value(holdings, date):
    prices = get_prices([h["ticker"] for h in holdings], date)
    return sum([h["quantity"] * prices[h["ticker"]] for h in holdings])


def moving_average(a, n=3):
    a = np.array(a)
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1 :] / n


def run_test(
    df,
    # listen after this time
    min_time="09:45",
    sell_after_gain=0.15,
    sell_after_loss=-0.06,
    # sell when reach % days to expiry
    sell_perc_to_expiry=1,
    top_n_tickers=50,
    # frequency penalty for puts
    put_penalty=-1,
    # min occurence before consider
    call_occurences=2,
    # call/put ratio
    cp_ratio_min=0,
    # position size when buying
    target_pos=0.1,
    max_days_to_exp=7,
    min_premium=20000,
    max_premium=1000000,
    unusual_only=False,
    starting_balance=25000,
    simulated_leverage=2,
    # only take positions when spy above ema
    spy_ema=True,
    spy_ema_val=13,
):
    holdings = []
    balance = starting_balance
    prev_day = df.Time.iloc[0].format("YYYY-MM-DD")
    prev_day = arrow.get(prev_day).shift(days=-1)

    # track balance hist and SPY benchmark
    balance_hist, benchmark = [balance], [balance]
    x_dates = [prev_day.format("YYYY-MM-DD")]
    spy_quantity = balance / get_price("SPY", prev_day)

    # SPY prices for EMA
    spy_prices = []
    current_ma = 0

    # count ticker frequencies each day
    init_occurences = {ticker: 0 for ticker in df.Ticker}
    occurences = init_occurences
    day_calls, day_puts = 1, 1

    counter = Counter()
    for index, row in tqdm(df.iterrows(), total=len(df)):
        date = row.Time

        # not tradable
        if row.Ticker not in tradable_assets:
            continue

        counter[row.Ticker] += 1
        counts = counter.most_common(top_n_tickers)

        # not in top n tickers
        if row.Ticker not in [x[0] for x in counts]:
            continue

        # count calls and puts
        if row["C/P"] == "CALLS":
            day_calls += 1
            occurences[row.Ticker] += 1
        else:
            day_puts += 1
            occurences[row.Ticker] -= put_penalty

        # new day
        day_compare = arrow.get(date.format("YYYY-MM-DD"))
        if day_compare > prev_day:
            # reset counts
            pops = []
            occurences = init_occurences
            day_calls, day_puts = 1, 1

            for idx, holding in enumerate(holdings):
                sell_price = get_price(holding["ticker"], prev_day)

                if abs(sell_price / holding["entry"] - 1) > 0.5:
                    sell_price = holding["entry"]
                    print(
                        f"WARNING: irregular price change: {holding['entry']} to {sell_price} "
                        f"({holding['ticker']}) on {prev_day.format('YYYY-MM-DD')}. "
                        "Ignoring position results"
                    )

                cost = holding["entry"] * holding["quantity"]
                value = sell_price * holding["quantity"]
                gain = (value - cost) * simulated_leverage

                # sell if held % to expiration
                if date >= holding["held_thres"]:
                    pops.append(idx)
                    balance += cost + gain

                # sell if gain exceeds thresh
                elif value / cost - 1 > sell_after_gain:
                    pops.append(idx)
                    balance += cost + gain

                # sell if loss exceeds thresh
                elif value / cost - 1 < sell_after_loss:
                    pops.append(idx)
                    balance += cost + gain

            # drop sold positions
            for pop in reversed(pops):
                holdings.pop(pop)

            # log history
            cur_value = balance + holdings_value(holdings, prev_day)
            balance_hist.append(cur_value)
            x_dates.append(day_compare.format("YYYY-MM-DD"))

            # track benchmark
            spy_price = get_price("SPY", prev_day)
            benchmark.append(spy_quantity * spy_price)
            spy_prices.append(spy_price)

            # update EMA
            if len(spy_prices) > spy_ema_val + 1:
                current_ma = moving_average(spy_prices, n=spy_ema_val)[-1]

            prev_day = day_compare

        # not enough money to do anything
        if balance < 150:
            continue

        # high enough call/put ratio
        if day_calls / day_puts < cp_ratio_min:
            continue

        # enough calls on this ticker
        if occurences[row.Ticker] < call_occurences:
            continue

        if row.Premium > max_premium or row.Premium < min_premium:
            continue

        # does not exceed min time of day
        if date < arrow.get(f"{date.format('YYYY-MM-DD')} {min_time}"):
            continue

        exp = row.Expiry
        e = dt.date(exp.year, exp.month, exp.day)
        s = dt.date(date.year, date.month, date.day)

        # expiry too far out
        days_to_expiry = np.busday_count(s, e)
        if days_to_expiry > max_days_to_exp:
            continue

        if not row.Spot > 0:
            continue

        # calculate position size
        net_value = balance + holdings_value(holdings, row.Time)
        quantity = max(1, int(target_pos * net_value / row.Spot))
        pos_value = quantity * row.Spot

        # can't afford position
        if pos_value > balance:
            continue

        # buy only when above EMA
        if spy_ema and current_ma > spy_prices[-1]:
            continue

        new_pos = {
            "ticker": row.Ticker,
            "entry": row.Spot,
            "long": row["C/P"] == "CALLS",
            "sellby": row.Expiry,
            "quantity": quantity,
            "entrydate": date,
            "held_thres": date.shift(days=int(sell_perc_to_expiry * days_to_expiry)),
        }

        holdings.append(new_pos)
        balance -= pos_value

    balance += holdings_value(holdings, prev_day.format("YYYY-MM-DD"))

    ret = balance / starting_balance - 1
    days = (df.Time.iloc[-1] - df.Time.iloc[0]).days
    annualized = (1 + ret) ** (365 / days) - 1
    history = np.array(balance_hist)
    ret_hist = history[1:] / history[:-1] - 1

    print(f"\n\nbalance: ${balance:.0f}")
    print("return:", f"{ret*100:.2f}%")
    print(f"annualized return: {annualized*100:.2f}%")
    print(f"average loss:", np.average(ret_hist[np.where(ret_hist < 0)[0]]))
    print(f"sharpe ratio: {ret/np.std(ret_hist):.2f}")

    # sortino ratio
    ret_hist[np.where(ret_hist > 0)[0]] = 0
    ret_hist = ret_hist ** 2
    down_stdev = np.sqrt(ret_hist.mean())
    sortino_ratio = ret / down_stdev
    print(f"sortino ratio: {sortino_ratio:.2f}")

    # return history of trades and SPY
    return_hist, return_hist_bench = [], []
    for i in range(len(balance_hist) - 1):
        return_hist.append(balance_hist[i + 1] / balance_hist[i] - 1)
        return_hist_bench.append(benchmark[i + 1] / benchmark[i] - 1)

    return_hist_diff = np.array(return_hist) - np.array(return_hist_bench)
    annualized_ir = np.sqrt(days) * return_hist_diff.mean() / return_hist_diff.std()
    print(f"IR: {annualized_ir:.3f}")

    # find drawdown
    record_high = 0
    from_high = []
    span = []
    for hist_bal in history:
        if hist_bal > record_high:
            record_high = hist_bal

        from_high.append(hist_bal / record_high - 1)
        span.append(f"${record_high:.2f} to ${hist_bal:.2f}")

    rec_idx = list(sorted(zip(from_high, span), key=lambda x: x[0]))[0]
    print(f"biggest drawdown: {sorted(from_high)[0]*100:.2f}%   ({rec_idx[1]})")

    # plot returns
    x_dates = [dt.datetime.strptime(d, "%Y-%m-%d").date() for d in x_dates]
    plt.figure(figsize=(20, 10))
    plt.plot(x_dates, balance_hist)
    plt.savefig(f"run_results.png")


if __name__ == "__main__":
    data_dir = "hist_data"
    df = pd.concat(
        [pd.read_csv(f"{data_dir}/{filename}") for filename in os.listdir(data_dir)]
    )
    df = clean_df(df)
    print(f"entries: {len(df)}\nrunning backtest")
    run_test(df)
