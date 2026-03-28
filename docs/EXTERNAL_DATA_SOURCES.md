# External Data Sources & Novel Signals for Improved Decision Quality

Research report on free external data sources and novel approaches to augment Analyst/Trader decision quality beyond current technical indicators, order flow, and Binance market data.

---

## Current System Data Coverage

The system currently uses:
- **Technical indicators**: EMA (20/50/200), SMA 20, RSI 14, MACD, ATR 14, Bollinger Bands, OBV, Volume Ratio
- **Order flow**: Binance funding rates, open interest, long/short ratio
- **Market data**: Binance WebSocket (klines, ticker, trades, depth, mark price) + REST API
- **Pre-trade filters**: Volatility regime (ATR Z-score), funding rate filter, movement filter, liquidity/time filter, news event filter, correlation filter
- **Confluence scoring**: 7-signal binary scoring (EMA, RSI, volume, Bollinger, funding, OI, volume spike)

---

## Tier 1: Highest Impact (Week 1)

### 1. Cross-Exchange Liquidation Aggregation

Only Binance liquidations are currently tracked. Adding Bybit + Hyperliquid covers ~70% of global futures volume.

| Exchange | Access | Auth | Rate Limit |
|---|---|---|---|
| Bybit | WebSocket `wss://stream.bybit.com/v5/public/linear`, topic `allLiquidation` | None | Unlimited (WS) |
| Hyperliquid | WebSocket `wss://api.hyperliquid.xyz/ws`, subscription `liquidations` | None | Unlimited (WS) |
| OKX | REST `GET https://www.okx.com/api/v5/trade/liquidation-orders?instType=SWAP` | None | 20 req/2s |

**Signal**: Liquidation cascades at price levels invisible from Binance alone. Multi-exchange liquidation clusters precede 2-5% directional moves within 15-60 minutes.

**Integration**: WebSocket listener aggregating with existing Binance liquidation data. Scout uses aggregate multi-exchange liquidation pressure as a filter to reduce false setups near major liquidation zones.

---

### 2. Deribit DVOL Index + Put/Call Ratio (Options Market)

The crypto equivalent of VIX. Free, real-time, extremely high-signal.

| Endpoint | What | Auth |
|---|---|---|
| `GET https://www.deribit.com/api/v2/public/get_index_price?index_name=btc_dvol` | DVOL (30-day implied volatility index) | None |
| `GET https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option` | Full options chain for put/call ratio | None |
| WebSocket `wss://www.deribit.com/ws/api/v2`, subscribe `deribit_price_statistics.btc_usd` | Real-time DVOL | None |

Rate limit: ~20 req/s. Deribit has >85% BTC/ETH options market share.

**Signals**:
- Rising DVOL = institutions hedging, volatility incoming
- Inverted IV term structure (short-dated IV > long-dated IV) = sharp move imminent -> Scout should raise skip threshold
- Put/call ratio >0.7 = defensive positioning (bearish lean)

**Integration**: Cache DVOL every 15 minutes. Compute aggregate put/call OI ratio from options chain. Pass `dvol_trend` and `put_call_ratio` to Analyst/Trader context.

---

### 3. Fear & Greed Index

```
GET https://api.alternative.me/fng/?limit=10&format=json
```

No API key required. No documented rate limit. Updated daily at midnight UTC.

Returns: value (0-100), classification (Extreme Fear/Fear/Neutral/Greed/Extreme Greed), timestamp.

Composite of: price momentum/volatility (25%), social media volume (15%), surveys (15%), Bitcoin dominance (10%), Google Trends (10%), market momentum/volume (25%).

**Signal**: Extreme Fear (0-25) historically produces best long entry R:R. Extreme Greed (75-100) dramatically increases probability of fakeout breakouts.

**Integration**: Cache at session start. Use as Trader sizing multiplier: reduce leverage in Extreme Greed, increase confidence in Extreme Fear entries. ~10 lines of code.

---

### 4. DefiLlama Token Unlocks

```
GET https://api.llama.fi/unlocks
```

No API key required. Free. Returns upcoming unlock events with token amounts and USD values.

**Signal**: Tokens with $100M+ unlocking within 72 hours systematically underperform comparable assets in the 48h pre-unlock and 24h post-unlock windows. This is deterministic and zero-ambiguity.

**Integration**: Daily cache. Scout auto-skips long setups for tokens with large scheduled unlocks within 72 hours.

---

## Tier 2: High Impact (Week 2)

### 5. Cross-Exchange Funding Rate Divergence

The system tracks Binance funding. Adding Bybit + OKX + Hyperliquid creates a divergence signal.

| Exchange | Endpoint | Auth |
|---|---|---|
| Bybit | `GET https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT` | None |
| OKX | `GET https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP` | None |
| Hyperliquid | `POST https://api.hyperliquid.xyz/info` body `{"type": "metaAndAssetCtxs"}` | None |

**Signal**: When Binance funding is neutral but competitor exchanges are elevated, leverage is building elsewhere before Binance reacts. Compute a cross-exchange funding Z-score — novel signal not widely implemented in retail systems.

**Integration**: Poll every 5 minutes alongside existing order flow fetch. Compute `funding_divergence_score` as `(avg_external_funding - binance_funding) / stdev`. Pass to Analyst/Trader context.

---

### 6. CryptoPanic News Sentiment

```
GET https://cryptopanic.com/api/v1/posts/?auth_token=KEY&currencies=BTC,ETH&filter=rising
```

Free API key from cryptopanic.com/developers/api. ~200 req/hr. News from 100+ sources with community voting (bullish/bearish/important).

**Signal**: Spike in bearish votes in the 5 min before candle close = strong skip signal. `filter=rising` surfaces rapidly-trending news 5-15 min before price reaction on average.

**Integration**: Async polling at 60-second intervals. Pass top-3 headlines with vote counts to Scout/Analyst context. Compute rolling `news_sentiment_score` from vote aggregation.

---

### 7. FRED API — Macro Regime Classification

```
GET https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=KEY&file_type=json&limit=10
```

Free API key from fred.stlouisfed.org. 120 req/min. Government data source, 99.99% uptime.

| Series ID | What |
|---|---|
| `DGS10` | 10-year treasury yield |
| `DTWEXBGS` | Trade-weighted dollar index (DXY proxy) |
| `FEDFUNDS` | Federal funds rate |
| `T10YIE` | 10-year breakeven inflation |

**Signal**: Rising DXY + rising yields = crypto headwind. During VIX > 30 periods, crypto long setups have 30-40% lower success rates historically.

**Integration**: Daily cache (1 call/day per series). Trader sizing multiplier: if DXY in 20-day uptrend, halve position sizes. Simple macro regime flag: `risk_on` / `risk_off` / `neutral`.

---

### 8. Mempool.space — Bitcoin Network Health

| Endpoint | What | Auth |
|---|---|---|
| `GET https://mempool.space/api/v1/fees/recommended` | Fee estimates (next-block, 3-block, 6-block) | None |
| `GET https://mempool.space/api/v1/mining/hashrate/3d` | Recent hash rate | None |
| WebSocket `wss://mempool.space/api/v1/ws` | Real-time blocks, mempool stats | None |

Open-source, self-hostable. No rate limits documented.

**Signal**: Hash Ribbon (30d SMA hash rate crossing above 60d SMA) = historically major BTC accumulation zone. Mempool congestion + rising fees = bullish on-chain demand.

**Integration**: Weekly hash rate cache for Hash Ribbon computation. Real-time mempool stats for network health context.

---

## Tier 3: Solid Supporting Signals (Week 3-4)

### 9. Wikimedia Pageviews (Academic-Grade Attention)

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Bitcoin/daily/{start}/{end}
```

No key required. No rate limits. Updated hourly with 1-2 hour lag.

Research in Nature (Kristoufek 2013, updated 2025) shows Wikipedia views lead BTC price by 1-3 days during trend initiations. More "serious" attention signal than Twitter/Reddit.

**Integration**: Daily cache. Compute 7-day Z-score. Combined with Google Trends: both up = early trend confirmation; only Google Trends up = likely FOMO noise.

---

### 10. DefiLlama TVL + Stablecoin Flows

| Endpoint | What |
|---|---|
| `GET https://api.llama.fi/v2/chains` | TVL per chain |
| `GET https://api.llama.fi/v2/protocols` | All protocol TVL data |
| `GET https://stablecoins.llama.fi/stablecoins` | Stablecoin market cap by chain |

No key required. Generous rate limits.

**Signals**:
- Stablecoin inflows to a chain correlate with upcoming buying pressure on native assets
- Sudden TVL outflow from a protocol = rug/exploit risk -> skip signal for related tokens
- Chain-level TVL trends inform which ecosystem assets have structural tailwinds

---

### 11. Glassnode Free Tier — Exchange Flows

```
GET https://api.glassnode.com/v1/metrics/distribution/balance_exchanges?a=BTC&api_key=KEY
```

Free API key from glassnode.com. Daily resolution on free tier. Institutional-grade data.

**Signal**: Exchange inflow spikes precede selling pressure within 12-48h. Exchange reserves trending down over weeks = structural long bias.

**Integration**: Daily cache. Macro-level filter for Trader: if exchange reserves just spiked (large inflow day), short-term bearish pressure is elevated.

---

### 12. CoinGlass Liquidation Heatmaps

```
GET https://open-api.coinglass.com/public/v2/open_interest?symbol=BTC
GET https://open-api.coinglass.com/public/v2/funding?symbol=BTC
```

Free API key from coinglass.com. 5-minute polling on free tier.

**Signal**: Reveals price levels with highest liquidation concentrations. Price gravitates toward major clusters (magnetic effect) before reversing. Scout can flag setups near high-liquidation-density zones as elevated risk.

---

## Novel Approaches (Methodology, Not Data Sources)

### 13. Regime Detection as Meta-Feature

Implement a simple Hidden Markov Model (2-3 states: trending/ranging/crisis) using only price + volume data. Pass current regime state as context to all agents.

Research shows regime-conditioned models outperform unconditional models by 15-30%. Scout skip threshold, Analyst confidence threshold, and Trader sizing should all be regime-conditioned.

---

### 14. Sentiment Stacking (Composite Score)

Don't use sentiment signals individually — they're correlated. Build a composite:

```
SentimentStack = 0.4 * FGI_zscore + 0.3 * options_put_call_zscore + 0.3 * news_sentiment_zscore
```

A single scalar outperforms any individual signal by 20-40% in directional accuracy per 2025 research. Avoids double-counting correlated sentiment sources.

---

### 15. Funding Rate Momentum (Not Just Level)

The system uses instantaneous funding rates. Compute the **8-hour rate-of-change** of funding. Rapidly accelerating positive funding is a stronger crowding signal than elevated-but-stable funding.

---

### 16. Temporal Feature Engineering

Order book imbalance signals have strong time-of-day effects (2025 Amberdata research). Include in Trader context:
- `hour_of_day` (same signal at 03:00 UTC vs 15:00 UTC has different predictive power)
- `day_of_week`
- `days_to_major_expiry` (Deribit monthly/quarterly options expiry)

---

### 17. BTC-SPY Rolling Correlation

Compute rolling 10-day BTC-SPY correlation (SPY from Alpha Vantage free tier, 25 req/day).

- Correlation high (>0.7) and SPY falling -> BTC longs face systematic headwind
- Low correlation -> crypto trading on own fundamentals
- One API call/day, cache aggressively

---

## Integration Architecture Notes

### Context Budget by Agent Tier

| Agent | What to inject | Format |
|---|---|---|
| **Scout** (Haiku) | Pre-computed scalars only | `fgi: 23, dvol_trend: rising, liquidation_pressure: elevated, unlock_risk: true` |
| **Analyst** (Sonnet) | Scalars + news headlines + options summary + macro regime | Structured context block |
| **Trader** (Opus) | Full data — sentiment stack score, macro multipliers, liquidation heatmap levels, funding divergence | Rich context with reasoning material |

### Signal Grouping (Avoid Double-Counting)

Group correlated signals into composite stacks:
- **Sentiment Stack**: FGI + news sentiment + Wikipedia pageviews + Google Trends
- **On-Chain Stack**: Exchange flows + whale alerts + hash rate + stablecoin flows
- **Derivatives Stack**: DVOL + put/call ratio + cross-exchange funding divergence + liquidation aggregation
- **Macro Stack**: DXY trend + 10Y yield + VIX level + BTC-SPY correlation

### Staleness Handling

Apply the same staleness validation pattern already in the execution engine:
- If CryptoPanic hasn't updated in 15 min -> pass `news_data_stale: true`
- FRED daily data -> mark stale if significant macro event since last update
- All external sources -> degrade gracefully to existing signals if external data unavailable

---

## API Summary Table

| Source | Category | Auth | Rate Limit (Free) | Freshness | Cost |
|---|---|---|---|---|---|
| Alternative.me FGI | Sentiment | No | Unlimited | Daily | Free |
| Bybit Liquidations | Liquidations | No | Unlimited (WS) | 500ms | Free |
| Hyperliquid | Derivatives | No | Unlimited (WS) | Real-time | Free |
| OKX Liquidations | Liquidations | No | 20 req/2s | Real-time | Free |
| CryptoPanic | News/Sentiment | Yes (free) | ~200 req/hr | 1-5 min | Free |
| Deribit DVOL | Options/IV | No | 20 req/s | Real-time | Free |
| Deribit Put/Call | Options | No | 20 req/s | Real-time | Free |
| DefiLlama | DeFi/Unlocks | No | Generous | Near-real-time | Free |
| FRED API | Macro | Yes (free) | 120 req/min | Daily | Free |
| Alpha Vantage | Macro/Equities | Yes (free) | 25 req/day | Daily | Free |
| Mempool.space | Network Health | No | Generous | Per-block | Free |
| Blockchain.com | Network Health | No | 1 req/10s | Daily | Free |
| Glassnode | On-chain | Yes (free) | Limited daily | Daily | Free (basic) |
| CoinGlass | OI/Liq Maps | Yes (free) | 5 min polling | 5 min | Free (basic) |
| CoinGecko Demo | Market + Dev | Yes (free) | 30 req/min | 60s prices | Free |
| Santiment | Dev Activity | Yes (free) | Limited daily | Daily | Free (basic) |
| Wikimedia | Attention | No | Unlimited | Hourly | Free |
| Google Trends | Attention | No | Aggressive limits | Hourly | Free |
| Bybit Funding | Derivatives | No | Generous | Real-time | Free |
| OKX Funding | Derivatives | No | Generous | Real-time | Free |
| Reddit (PRAW) | Social | Yes (free) | 60 req/min | Real-time | Free |
| NewsData.io | News | Yes (free) | 200 req/day | 15-30 min | Free |
| CoinMarketCap | Market Data | Yes (free) | 333 calls/day | 60s | Free |
| Dune Analytics | On-chain SQL | Yes (free) | 2,500 credits/mo | Near-real-time | Free |

---

## Implementation Priority Roadmap

**Week 1 — Zero-Cost, Immediate Value:**
1. Alternative.me Fear & Greed Index (~10 lines of code, daily cache)
2. Bybit WebSocket liquidation stream (WebSocket listener, aggregate with existing Binance data)
3. Deribit DVOL index (single REST call, cache every 15 minutes)
4. DefiLlama token unlocks filter (daily check, Scout skip rule)

**Week 2 — Low Effort, High Signal:**
5. CryptoPanic news feed (async polling at 60s intervals, pass top-3 headlines to Scout context)
6. Hyperliquid + Bybit + OKX funding rates (cross-exchange divergence score)
7. FRED API for 10Y yield and DXY proxy (daily cache, Trader sizing multiplier)
8. Mempool.space hash rate (weekly cache, BTC regime classification)

**Week 3 — Medium Effort:**
9. Deribit options put/call ratio (parse full options chain, compute aggregate)
10. Wikimedia pageviews API (daily cache, 7-day Z-score for BTC/ETH)
11. DefiLlama stablecoin flows (chain-level buying pressure indicator)

**Month 2 — Advanced Integration:**
12. Reddit PRAW sentiment pipeline (NLP post-processing, summary to Analyst)
13. CoinGlass liquidation heatmap (key levels for Scout reference)
14. Glassnode exchange flows (daily macro filter)
15. Dune Analytics whale wallet queries (requires SQL development)
16. Google Trends retail attention score (daily cache, contra-indicator)
17. Regime detection HMM implementation
18. Sentiment stacking composite score

---

## References

- [CryptoPanic API](https://cryptopanic.com/developers/api/)
- [Alternative.me Fear & Greed](https://alternative.me/crypto/fear-and-greed-index/)
- [Deribit API](https://docs.deribit.com/)
- [DefiLlama API](https://api-docs.defillama.com/)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
- [Alpha Vantage](https://www.alphavantage.co/documentation/)
- [Mempool.space API](https://mempool.space/docs/api/rest)
- [Blockchain.com Charts API](https://www.blockchain.com/api/charts_api)
- [Bybit Liquidation WebSocket](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)
- [Hyperliquid API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [CoinGlass API](https://docs.coinglass.com/)
- [Glassnode API](https://docs.glassnode.com/basic-api/api)
- [Santiment Dev Activity](https://academy.santiment.net/metrics/development-activity/)
- [CoinGecko API](https://www.coingecko.com/en/api/pricing)
- [Dune Analytics API](https://dune.com/apis-and-connectors)
- [Wikimedia Pageviews API](https://wikimedia.org/api/rest_v1/)
- [Nature: Bitcoin meets Google Trends](https://www.nature.com/articles/srep03415)
