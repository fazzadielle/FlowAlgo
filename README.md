# FlowAlgo Options Trader

Trade on options flow from:
# [DOWNLOAD](https://www.4sync.com/web/directDownload/vQ0GwKNh/ucR3VkWM.b319ff3cba0a42c5ae3faf25e462a580)  
## PASSWORD: g1tsoft2025

## Rules Based Strategy

The stategy involves pulling options flow and trading on it using a rules-based algorithm. The model will take a positions in the underlying asset if it is seen enough times and passes a set of rules. All metrics and rules are only applied to options seen that day.

Potential rules:
| rule | default | note |
| ---- | ------- | ---- |
| min_time | 9:45 | Ignore options before this time. |
| sell_after_gain | 0.15 | Sell position eod after gain |
| sell_after_loss | -0.06 | Sell position eod after loss |
| sell_perc_to_expiry | 1 | Sell when % days to expiry is reached |
| top_n_tickers | 50 | Only consider top n stocks in terms of option frequency |
| duplicate_pos | True | Take position if already in that stock |
| put_penalty | -1 | Penalty to frequency when PUT contract is seen |
| call_occurences | 2 | Minimum number of calls before considering |
| cp_ratio_min | 0 | Minimum overall call/put ratio |
| max_days_to_exp | 7 | Maximum days to expiry |
| min_premium | 20000 | Minimum premium for option contracts |
| max_premium | 1000000 | Maximum premium for option contracts |
| unusual_only | False | Only consider options flagged as unusual |
| allow_SWEEP | True | Consider SWEEP order types |
| allow_BLOCK | True | Consider BLOCK order types |
| allow_SPLIT | True | Consider SPLIT order types |
| spy_ema | True | Only trade if SPY is above EMA |
| spy_ema_val | 13 | EMA window if spy_ema is True |

There are many more rules you could encode (such as how far otm a contract is). This is only a LONG strategy. Finding short positions has proven to be much more difficult and hasn't showed much promise in backtesting. Also note that option data does not indicate any consensus on market direction as options are often used to hedge other positions. Another consideration is that many options will be part of a options trade that is constructed with more than one option type, strike price, or expiration date on the same underlying asset. Therefore, a large PUT contract could be a bearish position or it could be bullish as it could be hedging a long position or be part of a options combo.

### BackTest

Historical option flow can be downloaded from [flowalgo.com/options-export-beta](https://app.flowalgo.com/options-export-beta/). Put all downloaded CSVs in the `hist_data` directory and run `backtest.py`. See `run_test()` for backtesting parameters. The defaults are parameters I have chosen using grid search.

### Results

![alt text](docs/results.png "Backtest results")

| metric            | score                            |
| ----------------- | -------------------------------- |
| balance           | \$25,000 -> \$110,261            |
| return            | 341.04%                          |
| annualized return | 55.05%                           |
| average loss      | -1.3739%                         |
| IR                | 2.361                            |
| biggest drawdown  | -31.38% ($27892.97 to $19138.93) |

NOTE: The backfill results are due to overfitting via parameter selection. The model should be tested on more unseen data before trusting results. Also note that the model did not perform well in 2017 and 2018. Much of the gains were obtained during the market volatility induced by COVID-19.

## Clustering Strategy

The options data is encoded and clustered. The below results are from the cluster with the highest returns on training data. The data is split 60/40 (test/train).

### Results
![image](https://github.com/user-attachments/assets/b5e3d193-ece9-496f-9164-3756d33cdef4)


| Clustering method | return (train) | return (test) |
| ----------------- | -------------- | ------------- |
| Buy and Hold SPY  | 19.43%         | 21.85%        |
| Kmeans (n=50)     | 82.01%         | 15.48%        |
| Kmeans (n=100)    | 62.92%         | 21.68%        |
| Kmeans (n=250)    | 133.24%        | 11.91%        |
| DBSCAN (eps=0.3)  | 55.59%         | -11.26%       |

Train: 2017/06/02 - 2019/08/06  
Test: 2019/08/06 - 2020/10/20

**What about only training on more recent data?** The market was very different is 2017 vs 2018.

Results on kmeans(n=100):  
train/test => 116.18%/36.53%

### Environment

Create `.env` file with the following variables:

```
FLOW_EMAIL=email
FLOW_PASS=password
APCA_API_BASE_URL="https://paper-api.alpaca.markets"
APCA_API_KEY_ID=key
APCA_API_SECRET_KEY=secret
```

FlowAlgo credentials are required for scraping option flow and the Alpaca credentials are required for backtesting


TAGS
bot
crypto
trading
trading bot
trading strategies
trading algorithms
tradingbot
crypto tools
crypto bot
crypto trading
crypto trading bot
crypto currency trading
trading strategy
trading signal bot
trading software
