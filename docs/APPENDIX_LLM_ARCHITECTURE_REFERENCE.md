# **Architectural Blueprint for LLM-Driven Autonomous Trading Systems: Integrating Anthropic Opus and PydanticAI**

## **Executive Summary**

The integration of Large Language Models (LLMs) into the high-stakes domain of algorithmic cryptocurrency trading represents a paradigm shift from deterministic, heuristic-based strategies to probabilistic, semantic reasoning engines. This transformation moves the needle from purely quantitative systems—which rely on rigid mathematical formulas and speed—to qualitative-quantitative hybrids capable of interpreting the "why" behind market movements. While traditional high-frequency trading (HFT) systems prioritize nanosecond latency, the architecture proposed herein prioritizes cognitive depth, utilizing **Anthropic’s Claude 3.5 Opus** as a "System 2" reasoning engine. This report provides an exhaustive, expert-level analysis of the architecture, implementation, and risk management required to build an institutional-grade trading bot using **Python** and **PydanticAI**.

The central thesis of this architecture is the rigorous **Decoupling of Reasoning and Execution**. We explore a Producer-Consumer design pattern where a high-performance, asynchronous "Spine" (the existing Binance connector) handles data ingestion and order execution, while the LLM acts as the "Brain," processing complex market states asynchronously. This report addresses the unique challenges of this integration: managing the significant inference latency of Opus (2-10 seconds), mitigating hallucination risks through strict schema validation, and engineering context windows that distill massive datasets into actionable intelligence. By leveraging PydanticAI’s robust type enforcement and dependency injection systems, we establish a "Validation Firewall" that ensures no AI-generated anomaly can threaten capital solvency.

## **1\. The Epistemology of AI in Financial Markets**

### **1.1 From Deterministic to Probabilistic Trading**

Historically, algorithmic trading has been defined by determinism. A standard moving average crossover strategy is binary: if the short-term average crosses the long-term average, a buy signal is generated—without ambiguity or hesitation. These "System 1" thinkers, to borrow from Daniel Kahneman’s dual-process theory, are fast, instinctive, and rigid. They excel in environments where speed is the primary edge but fail when contextual nuance is required. They cannot read a Federal Reserve press release, interpret a sudden shift in regulatory sentiment, or correlate a breakdown in correlation between Bitcoin and the Nasdaq with on-chain whale movements.1

The introduction of Large Language Models introduces "System 2" thinking to the trading stack. Claude 3 Opus, Anthropic’s most capable model, does not just process numbers; it processes *meaning*. It can evaluate the "texture" of a market. Is the volume declining on an upward move because of seller exhaustion or a lack of buyer interest? A deterministic algorithm sees only Volume\_t \< Volume\_t-1. An LLM, provided with the right context, can reason that this divergence, coupled with bearish news sentiment and an overbought RSI, constitutes a "fake-out" rather than a consolidation. This ability to synthesize unstructured data (news, sentiment, broad market context) with structured technical indicators allows for strategies that are adaptive rather than static.3

### **1.2 The Latency-Cognition Trade-off**

However, this cognitive capability comes at a steep price: latency. While a C++ HFT engine executes in microseconds, a call to the Claude 3 Opus API involves network transmission, tokenization, transformer inference (which is compute-bound and scales with context length), and de-tokenization. Total round-trip time (RTT) can range from 2 seconds for short prompts to over 10 seconds for complex, multi-step reasoning tasks.5

This physical constraint necessitates a fundamental shift in strategy design. One cannot build a scalping bot that chases order book imbalances using Opus; by the time the model decides to buy, the liquidity is gone. Instead, the architecture must focus on **Swing Trading** and **Intraday Trend Following**, where the decision horizon is measured in minutes or hours, not milliseconds. The system operates on a "tick-to-trade" cycle where the "tick" is a completed 15-minute or 1-hour candle, providing a stable window for the model to "think" without the market shifting radically under its feet.7

### **1.3 The Role of Anthropic Opus**

We select Claude 3 Opus over faster models (like Haiku or GPT-3.5) specifically for its reasoning fidelity. In financial trading, a false positive (buying into a crash) is infinitely more damaging than a false negative (missing a pump). Opus demonstrates superior performance in following complex instructions, adhering to negative constraints (what *not* to do), and performing multi-step logical deductions.6 Its large context window (200k tokens) allows for the ingestion of extensive historical price data, technical indicator logs, and even recent news headlines, creating a rich "state of the world" for every decision. The trade-off in speed is a deliberate architectural choice prioritizing **Precision over Velocity**.

## ---

**2\. System Architecture: The "Brain" and "Spine" Paradigm**

### **2.1 The Decoupled Event-Driven Model**

To reconcile the sluggishness of the LLM with the real-time demands of the crypto market, we must abandon synchronous, linear execution flow. A simple while True: loop that fetches data, calls the LLM, and then trades is doomed to fail; it would block heartbeats to the exchange, miss fills, and drift from real-time data.8

Instead, we implement a **Producer-Consumer Architecture** utilizing Python’s asyncio framework. This architecture separates the system into two distinct biological analogues:

1. **The Spine (System 1):** The deterministic, high-speed layer. This includes the Binance Connector (from your existing project), WebSocket managers, and the Order Execution Engine. It never sleeps, never blocks, and handles the "reflexes" of the bot—Stop Losses, Take Profits, and heartbeat maintenance.  
2. **The Brain (System 2):** The probabilistic, high-latency layer. This contains the PydanticAI Agent and the Anthropic Client. It wakes up only when triggered (e.g., on a candle close), performs deep analysis, and emits a high-level directive.1

### **2.2 Asynchronous Concurrency Patterns**

The system relies on an asyncio Event Loop to juggle these responsibilities. The "Spine" pushes normalized market data into a thread-safe asyncio.Queue, which the "Brain" consumes.

#### **2.2.1 The Data Ingest Loop (The Producer)**

This component connects to the Binance WebSocket API. Its sole responsibility is to maintain a local mirror of the market state. It processes distinct streams:

* kline\_15m: Updates the OHLCV (Open, High, Low, Close, Volume) data.  
* depth\_update: Maintains a local order book for liquidity analysis.  
* execution\_report: Listens for fill confirmations to update the bot's internal position state.

Crucially, this loop is **non-blocking**. It buffers incoming messages. If the LLM is busy "thinking" about the last candle, the Ingest Loop continues to process ticks, ensuring no data is lost and the local state remains pristine.8

#### **2.2.2 The Reasoning Loop (The Consumer)**

This loop monitors the MarketDataQueue. When a specific trigger condition is met (e.g., a candle closes), it snapshots the current state. This snapshot is immutable—even if the market moves while the LLM is thinking, the LLM analyzes the market *as it was* at the close of the candle. This prevents "data skew" where the model's reasoning is based on shifting sands.

The snapshot is transformed into a MarketContext object (a Pydantic model) and passed to the PydanticAI Agent. The Agent’s execution is awaited, yielding control back to the event loop so the Spine can continue its work. Once the Agent returns a TradeSignal, it is placed into an ExecutionQueue.14

#### **2.2.3 The Execution Loop (The Actuator)**

This loop consumes the ExecutionQueue. It does not blindly execute. It passes the TradeSignal through a **Risk Validator**. If the signal passes (e.g., valid size, safe stop-loss), the Spine translates it into an HTTP POST request to the Binance REST API. This loop also manages the lifecycle of the order—monitoring for partial fills and managing local stop-loss triggers if the exchange does not support server-side OCO (One-Cancels-Other) orders.2

### **2.3 Latency Management and "Thinking Time"**

Since Opus takes seconds to respond, the market price P\_t at the time of signal generation might differ from P\_now at the time of execution. To handle this:

1. **Limit Orders:** We strictly use Limit Orders, never Market Orders, for entry. The Agent suggests a limit price (e.g., "Buy at 65,000"). If the market has moved to 65,100, the order sits on the book. This avoids slippage.  
2. **Execution Tolerance:** The validation layer checks the "staleness" of the signal. If the reasoning took \> 30 seconds, the signal is discarded as expired.  
3. **Streaming:** We leverage PydanticAI's streaming capabilities (run\_stream) not for the final JSON, but to monitor the "Time to First Token" (TTFT). If the model hangs or networks stall, we can timeout early and retry.5

## ---

**3\. The PydanticAI Framework: Orchestration & Safety**

PydanticAI is the chosen framework because it treats LLM interaction as a rigorously typed software engineering problem, not a loose NLP script. In financial systems, "string parsing" is a vulnerability. PydanticAI mitigates this by enforcing schema adherence at the framework level.17

### **3.1 The Agent Lifecycle and Configuration**

The Agent is the core container. It encapsulates the model configuration, the system prompt, the tool definitions, and the dependency injection logic.

#### **3.1.1 Model Selection**

We configure the AnthropicModel specifically for Opus. We also set the max\_tokens parameter carefully—enough for a detailed Chain-of-Thought (CoT), but capped to prevent runaway loops that drain API credits.

Python

from pydantic\_ai import Agent, RunContext  
from pydantic\_ai.models.anthropic import AnthropicModel  
from pydantic import BaseModel

\# Configuration for the "Brain"  
model \= AnthropicModel(  
    'claude-3-opus-20240229',  
    api\_key='YOUR\_ANTHROPIC\_KEY',  
)

\# The Agent definition  
trader\_agent \= Agent(  
    model,  
    deps\_type=TradingDependencies, \# Strongly typed context injection  
    result\_type=TradeDecision,     \# Strongly typed output enforcement  
    retries=2                      \# Auto-retry on validation failure  
)

### **3.2 Dependency Injection: The RunContext**

A common anti-pattern in simple bots is using global variables for state (e.g., global current\_price). PydanticAI solves this via Dependency Injection. We define a TradingDependencies dataclass that carries everything the Agent needs to know *at runtime*. This makes the agent stateless and testable.17

The RunContext generic is parameterized with this dependency class. When the agent runs, the RunContext is passed to every tool and dynamic prompt, allowing them to access the "Spine's" live data in a thread-safe manner.

**Components of the Dependency Context:**

1. **Exchange Client:** The async wrapper for Binance (from your readme).  
2. **Market Data Cache:** A read-only view of the latest pandas DataFrame containing OHLCV and indicators.  
3. **Account State:** Current wallet balance (free/locked) and open positions.  
4. **Logger:** A structured logger for audit trails.

### **3.3 Dynamic System Prompts**

Static system prompts are insufficient for trading. The "rules of engagement" might change based on volatility. PydanticAI allows for dynamic system prompts using the @agent.system\_prompt decorator. This function runs *before* every inference call, allowing us to inject the current "Regime" into the prompt.16

*Example:* If market volatility (ATR) is high, the system prompt dynamically appends: "MARKET IS VOLATILE. REDUCE POSITION SIZING BY 50%. WIDEN STOP LOSSES." This ensures the LLM is primed for the specific environment of the current candle.20

## ---

**4\. Data Engineering: Constructing the Context Window**

The adage "Garbage In, Garbage Out" is critical here. The LLM's reasoning is bounded by the quality of the data it receives. We cannot simply dump raw JSON ticks into the prompt; it consumes too many tokens and obscures high-level patterns. We must perform "Feature Engineering" to summarize the market state.3

### **4.1 Feature Engineering and Normalization**

The "Spine" processes the raw 1-minute candles into a rich feature set before the LLM ever sees them. We use libraries like pandas-ta to compute deterministic indicators. While Opus *can* calculate RSI from a list of numbers, it is prone to arithmetic hallucination. It is far safer and cheaper to provide the calculated value.

**Key Features to Inject:**

* **Trend:** EMAs (20, 50, 200), MACD (Line, Signal, Histogram).  
* **Momentum:** RSI (14), Stochastic Oscillator.  
* **Volatility:** Bollinger Band Width (BBW), Average True Range (ATR).  
* **Volume:** On-Balance Volume (OBV), Volume/SMA(Volume) ratio.

### **4.2 Prompt-Ready Data Formatting**

How we present this data matters. Research indicates that LLMs parse **Markdown Tables** and **JSON** most effectively for structured data.21 We format the recent history (last 20 candles) as a Markdown table to give the model a visual sense of the trend, while the "Current Snapshot" is provided as a JSON object for precision.

**Table 1: Example of Context Window Data Formatting**

| Component | Format | Purpose |
| :---- | :---- | :---- |
| **Current Snapshot** | JSON | Exact values for decision logic (Price, Balance). |
| **Recent History** | Markdown Table | Visualizing trend/flow (Last 10-20 candles). |
| **Active Positions** | JSON List | Managing existing risk (Entry Price, PnL). |
| **News/Sentiment** | Bullet Points | Contextualizing price action (External factors). |

### **4.3 Context Window Management (RAG vs. Sliding Window)**

Opus has a 200k token window, but filling it increases latency and cost. We employ a Sliding Window approach, feeding only the relevant timeframe (e.g., last 4 hours of 15m candles).  
For deeper history, we can implement Retrieval Augmented Generation (RAG). We store historical "setups" in a vector database. When the current market state matches a historical pattern (e.g., "Bull Flag"), we retrieve the outcome of that past event and feed it to Opus: "In the last 3 instances of this pattern, price rose 5% twice and failed once." This grounds the LLM in empirical reality.22

## ---

**5\. Prompt Engineering: The Cognitive Blueprint**

The prompt is the interface through which we align the LLM's probabilistic nature with our trading goals. We do not ask "What should I do?"; we command a specific analytical process.

### **5.1 The Persona and Governance**

We establish a persona that prioritizes risk management over profit. The prompt explicitly defines the agent's psychological profile:

"You are a disciplined, risk-averse institutional trader. You prioritize capital preservation. You are skeptical of breakouts until confirmed by volume. You do not chase pumps." 24

### **5.2 Chain of Thought (CoT) Architecture**

To minimize hallucination, we require the model to output its reasoning *before* its decision. This forces the transformer to attend to all input tokens before committing to a BUY or SELL token. We structure the prompt to demand a specific sequence of thoughts 1:

1. **Market Classification:** Is the market trending or ranging? (Check EMAs).  
2. **Key Levels:** Identify Support and Resistance (Check pivot points/Bollinger Bands).  
3. **Momentum Analysis:** Is the move supported by RSI/MACD?  
4. **Volume Analysis:** Is volume confirming the price action?  
5. **Invalidation:** Where does this thesis fail? (Stop Loss location).  
6. **Conclusion:** Final Verdict.

### **5.3 The Master Prompt Template**

Below is the structure of the system prompt injected into the PydanticAI Agent. Note the use of XML-like tags (common in Anthropic prompting) to delineate sections.27

\<system\_role\>  
You are a Senior Crypto Quantitative Analyst. Your goal is to analyze the provided MarketState and output a structured TradeDecision.  
\</system\_role\>  
\<output\_format\>  
You must use the TradeDecision tool to return your response. Do not output raw text outside the tool call.  
\</output\_format\>

## ---

**6\. The Validation Layer: The "Firewall"**

This is the most critical innovation in this architecture. We assume the LLM *will* eventually make a mistake—it will hallucinate a price, invert a stop-loss, or bet the entire account on a whim. The **Validation Layer**, implemented via Pydantic validators, acts as a firewall that blocks these invalid signals from ever reaching the exchange.28

### **6.1 Schema Definition and Validation**

We define the TradeDecision model not just as a data container, but as a rule engine. Pydantic's @model\_validator allows us to enforce cross-field logic.

**Validation Rules Enforced in Code:**

1. **Directional Logic:** If Action \== BUY, then Stop Loss \< Entry \< Take Profit. The inverse applies to SELL.  
2. **Risk/Reward Ratio:** (Take Profit \- Entry) / (Entry \- Stop Loss) must be \>= 1.5. If the LLM proposes a trade with poor R:R, it is rejected.  
3. **Price Sanity:** The Entry price must be within X% of the current market price (preventing fat-finger hallucinations like buying BTC at $100).  
4. **Confidence Threshold:** If Confidence \< 0.7, the Action is coerced to WAIT.

### **6.2 Self-Correction Loop**

PydanticAI supports a feedback loop. If the validator raises a ValueError (e.g., "Stop Loss is above Entry for a Long trade"), this error is caught and sent *back* to Opus as a new user message:

"Error: Your proposed Stop Loss (65000) is above your Entry (64000). This is invalid for a Long position. Please correct this."

Opus, seeing this error, will regenerate the response with corrected values. This "Retry" mechanism significantly increases the reliability of the system.29

## ---

**7\. Tool Implementation: Giving the Agent "Hands"**

The Agent needs to interact with the world. We define "Tools" using the @agent.tool decorator. These functions are exposed to the LLM, which can invoke them during its reasoning process.31

### **7.1 Read-Only vs. Execution Tools**

We strictly categorize tools into "Safe" (Read-Only) and "Unsafe" (State-Changing).

* **Safe Tools:** get\_order\_book, get\_recent\_trades, calculate\_pivot\_points. The Agent can call these freely to gather more info.  
* **Unsafe Tools:** execute\_order. **Crucially, we do NOT give the Agent direct access to this tool.** The Agent returns a *Decision Object*. The "Spine" (deterministic code) executes the order. This prevents a "loop of death" where the Agent rapidly executes 100 orders due to a prompt loop.

### **7.2 Implementing a Context-Aware Tool**

Here is how we implement a tool that uses the injected RunContext to fetch live data.

Python

@trader\_agent.tool  
async def get\_liquidity\_depth(ctx: RunContext, percent\_distance: float) \-\> dict:  
    """  
    Calculates the bid/ask liquidity within a certain % distance from current price.  
    Useful for determining if there is enough liquidity to enter/exit without slippage.  
    """  
    \# Access the shared exchange connector from dependencies  
    exchange \= ctx.deps.exchange\_client  
    symbol \= ctx.deps.symbol  
      
    \# Fetch live order book  
    order\_book \= await exchange.fetch\_order\_book(symbol)  
      
    \# Calculate liquidity (simplified logic)  
    current\_price \= (order\_book\['bids'\] \+ order\_book\['asks'\]) / 2  
    target\_bid \= current\_price \* (1 \- percent\_distance/100)  
    target\_ask \= current\_price \* (1 \+ percent\_distance/100)  
      
    bid\_liquidity \= sum(\[vol for price, vol in order\_book\['bids'\] if price \>= target\_bid\])  
    ask\_liquidity \= sum(\[vol for price, vol in order\_book\['asks'\] if price \<= target\_ask\])  
      
    return {  
        "bid\_liquidity": bid\_liquidity,  
        "ask\_liquidity": ask\_liquidity,  
        "unit": "Base Asset"  
    }

## ---

**8\. Execution & Order Management: The "Spine" Implementation**

This section details the integration with your existing Binance connector. We assume a standard ccxt-style async interface.

### **8.1 The Execution Engine**

The Execution Engine is a pure Python class that takes the validated TradeDecision and manages the logistics of the trade.

1. **Position Sizing:** The Agent suggests a "Conviction" (e.g., "High"). The Execution Engine translates this into a dollar amount based on the RiskManager settings (e.g., High Conviction \= 2% of equity, Low \= 0.5%). This keeps the LLM away from the raw bankroll.28  
2. **Order Placement:** It places the entry Limit Order.  
3. **Monitor:** It watches the WebSocket execution\_report.  
4. **OCO Logic:** Once the entry is filled, it *immediately* places the Stop Loss and Take Profit orders. If the exchange supports OCO (One-Cancels-Other), it uses that. If not, it manages the logic locally (if TP is hit, cancel SL).

### **8.2 Error Handling and Resilience**

The crypto market is 24/7; the bot must recover from failures.

* **API Rate Limits:** The Binance connector must implement a TokenBucket limiter. If the LLM generates signals too fast, the Execution Engine queues them or discards them to protect the API key.33  
* **Websocket Disconnects:** The Ingest Loop must have an automatic reconnection strategy with exponential backoff.  
* **State Persistence:** All active orders and positions must be persisted to a local database (SQLite/PostgreSQL). If the bot crashes and restarts, it reloads the state from the DB and reconciles it with the exchange (fetching open orders) to ensure it doesn't "lose track" of a trade.7

## ---

**9\. Operational Resilience and Future Proofing**

### **9.1 Handling Hallucinations and Adversarial Inputs**

Even with Pydantic, the LLM might hallucinate "reasonable but wrong" data (e.g., citing a news event that didn't happen). To mitigate this:

* **Grounding:** Provide news headlines in the context window. If the LLM cites a news event not in the provided list, the prompt instructions should command it to flag low confidence.  
* **Consistency Checks:** If the LLM says "Price is crashing" but the provided MarketState shows Price\_Change\_1h \= \+2%, the Validator can catch this contradiction if we implement cross-reference validation logic (requiring the LLM to cite the specific data point in the input).

### **9.2 Cost Management**

Opus is expensive. To optimize:

* **Tiered Intelligence:** Use a cheaper model (Claude 3 Haiku) to scan the market every minute. Only if Haiku detects a potential setup (Confidence \> 0.5) do we wake up Opus for the "Final Decision." This "Mixture of Agents" approach saves costs while maintaining high capability.35  
* **Prompt Caching:** Cache the static parts of the system prompt and the few-shot examples. This dramatically reduces the input token cost.36

## ---

**10\. Conclusion**

The architecture presented defines a state-of-the-art approach to AI-driven trading. By respecting the distinct strengths of Probabilistic AI (reasoning, synthesis) and Deterministic Code (speed, safety, execution), we create a system that is greater than the sum of its parts. The **Decoupled Producer-Consumer** pattern solves the latency issue; **PydanticAI** solves the reliability issue; and **Anthropic Opus** solves the intelligence issue.

The resulting bot is not a "black box" but a "glass box"—transparent in its reasoning (via CoT logs), safe in its execution (via Validation Firewalls), and robust in its operation (via Asyncio concurrency). This is the blueprint for the next generation of institutional algorithmic trading.

## **11\. Implementation Reference Code**

### **11.1 The Core Agent (agent.py)**

Python

import os  
from datetime import datetime  
from typing import Literal, Optional, List  
from dataclasses import dataclass  
from pydantic import BaseModel, Field, model\_validator  
from pydantic\_ai import Agent, RunContext, ModelRetry  
from pydantic\_ai.models.anthropic import AnthropicModel

\# \--- 1\. Define the Data Contract (The Language) \---

class TradeDecision(BaseModel):  
    """The structured output expected from Claude Opus."""  
    action: Literal  
    confidence: float \= Field(ge=0.0, le=1.0, description="0.0 to 1.0 confidence score")  
    reasoning: str \= Field(..., description="Chain-of-thought analysis explaining the decision")  
    suggested\_entry: Optional\[float\] \= None  
    suggested\_stop\_loss: Optional\[float\] \= None  
    suggested\_take\_profit: Optional\[float\] \= None

    @model\_validator(mode='after')  
    def validate\_logic(self):  
        """ The Firewall: Validates that the trade makes mathematical sense. """  
        if self.action in:  
            \# Ensure all price fields are present  
            if not all(\[self.suggested\_entry, self.suggested\_stop\_loss, self.suggested\_take\_profit\]):  
                raise ValueError(f"Action is {self.action} but price targets are missing.")  
              
            \# BUY Logic: SL \< Entry \< TP  
            if self.action \== 'BUY':  
                if not (self.suggested\_stop\_loss \< self.suggested\_entry \< self.suggested\_take\_profit):  
                    raise ValueError("For BUY: Stop Loss must be \< Entry \< Take Profit.")  
                  
                \# Enforce min Reward:Risk ratio of 1.5  
                risk \= self.suggested\_entry \- self.suggested\_stop\_loss  
                reward \= self.suggested\_take\_profit \- self.suggested\_entry  
                if reward \< (1.5 \* risk):  
                    raise ValueError(f"Risk/Reward ratio {reward/risk:.2f} is too low (min 1.5).")

            \# SELL Logic: SL \> Entry \> TP  
            if self.action \== 'SELL':  
                if not (self.suggested\_stop\_loss \> self.suggested\_entry \> self.suggested\_take\_profit):  
                    raise ValueError("For SELL: Stop Loss must be \> Entry \> Take Profit.")  
          
        return self

\# \--- 2\. Define Dependencies (The Context) \---

@dataclass  
class TradingDeps:  
    symbol: str  
    current\_price: float  
    account\_balance: float  
    open\_positions: List\[dict\]  
    \# In a real app, this would be your Async Binance Client instance  
    exchange\_client: object 

\# \--- 3\. Configure the Model & Agent \---

model \= AnthropicModel(  
    'claude-3-opus-20240229',  
    api\_key=os.getenv('ANTHROPIC\_API\_KEY')  
)

trader \= Agent(  
    model,  
    deps\_type=TradingDeps,  
    result\_type=TradeDecision,  
    retries=2, \# Allow 2 self-correction attempts if validation fails  
    system\_prompt=(  
        "You are a Senior Quantitative Crypto Trader. "  
        "Your mandate is capital preservation. "  
        "Analyze the market state and provide a strictly validated trade decision."  
    )  
)

\# \--- 4\. Dynamic Prompt Injection \---

@trader.system\_prompt  
def inject\_market\_context(ctx: RunContext) \-\> str:  
    """Dynamically injects account state into the system prompt."""  
    return (  
        f"CURRENT CONTEXT:\\n"  
        f"- Symbol: {ctx.deps.symbol}\\n"  
        f"- Current Price: {ctx.deps.current\_price}\\n"  
        f"- Available Balance: ${ctx.deps.account\_balance:.2f}\\n"  
        f"- Active Positions: {len(ctx.deps.open\_positions)}\\n\\n"  
        "RISK RULES:\\n"  
        "- Do not risk more than 1% of Balance per trade.\\n"  
        "- If you have an open position for this symbol, action must be WAIT or CLOSE."  
    )

\# \--- 5\. Tool Definitions \---

@trader.tool  
async def check\_liquidity(ctx: RunContext, price\_level: float) \-\> str:  
    """Check if there is sufficient liquidity at a specific price level."""  
    \# Simulation of using the injected exchange client  
    \# await ctx.deps.exchange\_client.fetch\_order\_book(...)  
    return "Liquidity is HIGH. Slippage estimated \< 0.1%."

### **11.2 The Event Loop (main.py)**

Python

import asyncio  
from agent import trader, TradingDeps, TradeDecision  
\# Assuming 'connector' is your existing project's package  
from connector import BinanceAsyncClient   
from strategies import TechnicalAnalysis

async def main\_loop():  
    client \= BinanceAsyncClient(api\_key="...", api\_secret="...")  
    await client.connect()  
      
    symbol \= "BTC/USDT"  
      
    while True:  
        try:  
            \# 1\. THE SPINE: Fetch Data  
            candles \= await client.get\_recent\_candles(symbol, interval="15m", limit=50)  
            current\_price \= candles\[-1\].close  
            balance \= await client.get\_usdt\_balance()  
              
            \# 2\. FEATURE ENGINEERING: Prepare the data for the Brain  
            \# Calculate RSI, MACD, etc. locally  
            ta\_summary \= TechnicalAnalysis.analyze(candles)  
              
            \# 3\. CONSTRUCT DEPENDENCIES  
            deps \= TradingDeps(  
                symbol=symbol,  
                current\_price=current\_price,  
                account\_balance=balance,  
                open\_positions=, \# Fetch from client  
                exchange\_client=client  
            )  
              
            \# 4\. THE BRAIN: Run PydanticAI Agent  
            \# We pass the TA summary as the user prompt  
            print(f"\[{symbol}\] Thinking...")  
            result \= await trader.run(  
                f"Market Technical Summary:\\n{ta\_summary.to\_markdown()}",   
                deps=deps  
            )  
              
            decision: TradeDecision \= result.data  
            print(f"Decision: {decision.action} | Confidence: {decision.confidence}")  
            print(f"Reasoning: {decision.reasoning}")  
              
            \# 5\. THE SPINE: Execute  
            if decision.action \== 'BUY' and decision.confidence \> 0.8:  
                await client.place\_limit\_order(  
                    symbol=symbol,  
                    side='BUY',  
                    price=decision.suggested\_entry,  
                    quantity=calculate\_size(balance, decision.suggested\_entry)  
                )  
                \# OCO Logic for SL/TP would go here  
                  
        except Exception as e:  
            print(f"Error in loop: {e}")  
          
        \# Wait for next candle close  
        await asyncio.sleep(60)

if \_\_name\_\_ \== "\_\_main\_\_":  
    asyncio.run(main\_loop())

### **Citations**

1

#### **Источники**

1. Trade in Minutes\! Rationality-Driven Agentic System for Quantitative Financial Trading \- arXiv, дата последнего обращения: января 9, 2026, [https://arxiv.org/html/2510.04787v1](https://arxiv.org/html/2510.04787v1)  
2. Optimize tick-to-trade latency for digital assets exchanges and trading platforms on AWS | AWS Web3 Blog, дата последнего обращения: января 9, 2026, [https://aws.amazon.com/blogs/web3/optimize-tick-to-trade-latency-for-digital-assets-exchanges-and-trading-platforms-on-aws/](https://aws.amazon.com/blogs/web3/optimize-tick-to-trade-latency-for-digital-assets-exchanges-and-trading-platforms-on-aws/)  
3. Comparing LLM-Based Trading Bots: AI Agents, Techniques, and Results in Automated Trading | FlowHunt, дата последнего обращения: января 9, 2026, [https://www.flowhunt.io/blog/llm-trading-bots-comparison/](https://www.flowhunt.io/blog/llm-trading-bots-comparison/)  
4. How To Use LLMs as Your Crypto Trading Research Copilot \- Ledger, дата последнего обращения: января 9, 2026, [https://www.ledger.com/academy/topics/crypto/how-to-use-llms-as-your-crypto-trading-research-copilot](https://www.ledger.com/academy/topics/crypto/how-to-use-llms-as-your-crypto-trading-research-copilot)  
5. Reducing latency \- Claude Docs, дата последнего обращения: января 9, 2026, [https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)  
6. Claude Opus 4.5 \- API, Providers, Stats \- OpenRouter, дата последнего обращения: января 9, 2026, [https://openrouter.ai/anthropic/claude-opus-4.5](https://openrouter.ai/anthropic/claude-opus-4.5)  
7. High-frequency crypto trading bot architecture Part 1 | by Bertalan Kondrat | Medium, дата последнего обращения: января 9, 2026, [https://medium.com/@kb.pcre/high-frequency-crypto-trading-bot-architecture-part-1-48b880bfc85f](https://medium.com/@kb.pcre/high-frequency-crypto-trading-bot-architecture-part-1-48b880bfc85f)  
8. Python Asyncio for LLM Concurrency: Best Practices \- Newline.co, дата последнего обращения: января 9, 2026, [https://www.newline.co/@zaoyang/python-asyncio-for-llm-concurrency-best-practices--bc079176](https://www.newline.co/@zaoyang/python-asyncio-for-llm-concurrency-best-practices--bc079176)  
9. I asked Claude Opus 4.5 to autonomously develop a trading strategy. It is DESTROYING the market \- NexusTrade, дата последнего обращения: января 9, 2026, [https://nexustrade.io/blog/i-asked-claude-opus-45-to-autonomously-develop-a-trading-strategy-it-is-destroying-the-market-20251125](https://nexustrade.io/blog/i-asked-claude-opus-45-to-autonomously-develop-a-trading-strategy-it-is-destroying-the-market-20251125)  
10. Crypto Trading Bot: Architecture and Roadmap | by Vitalii Honchar \- Medium, дата последнего обращения: января 9, 2026, [https://vitalii-honchar.medium.com/crypto-trading-bot-architecture-and-roadmap-f3e26cf9956a](https://vitalii-honchar.medium.com/crypto-trading-bot-architecture-and-roadmap-f3e26cf9956a)  
11. Building a Multi-Agent AI Trading System: Technical Deep Dive into Architecture \- Medium, дата последнего обращения: января 9, 2026, [https://medium.com/@ishveen/building-a-multi-agent-ai-trading-system-technical-deep-dive-into-architecture-b5ba216e70f3](https://medium.com/@ishveen/building-a-multi-agent-ai-trading-system-technical-deep-dive-into-architecture-b5ba216e70f3)  
12. Producer-Consumer example comparing threading and asyncio | by Arshad Ansari, дата последнего обращения: января 9, 2026, [https://blog.hikmahtechnologies.com/producer-consumer-example-comparing-threading-and-asyncio-a91f498058c1](https://blog.hikmahtechnologies.com/producer-consumer-example-comparing-threading-and-asyncio-a91f498058c1)  
13. WebSocket architecture best practices: Designing scalable realtime systems, дата последнего обращения: января 9, 2026, [https://ably.com/topic/websocket-architecture-best-practices](https://ably.com/topic/websocket-architecture-best-practices)  
14. 3 essential async patterns for building a Python service | Elastic Blog, дата последнего обращения: января 9, 2026, [https://www.elastic.co/blog/async-patterns-building-python-service](https://www.elastic.co/blog/async-patterns-building-python-service)  
15. Understanding producer-consumer program with asyncio \- Stack Overflow, дата последнего обращения: января 9, 2026, [https://stackoverflow.com/questions/71568584/understanding-producer-consumer-program-with-asyncio](https://stackoverflow.com/questions/71568584/understanding-producer-consumer-program-with-asyncio)  
16. Agents \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/agents/](https://ai.pydantic.dev/agents/)  
17. Pydantic AI \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/](https://ai.pydantic.dev/)  
18. pydantic/pydantic-ai: GenAI Agent Framework, the Pydantic way \- GitHub, дата последнего обращения: января 9, 2026, [https://github.com/pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)  
19. Mastering PydanticAI: Enhancing AI Agents with Dependency Injection — Day 2 \- Medium, дата последнего обращения: января 9, 2026, [https://medium.com/@nninad/mastering-pydanticai-enhancing-ai-agents-with-dependency-injection-day-2-a11f8aa18f49](https://medium.com/@nninad/mastering-pydanticai-enhancing-ai-agents-with-dependency-injection-day-2-a11f8aa18f49)  
20. Building a Bank Support Agent using PydanticAI | by Dr. Nimrita Koul \- Medium, дата последнего обращения: января 9, 2026, [https://medium.com/@nimritakoul01/building-a-bank-support-agent-using-pydanticai-114a04886f9b](https://medium.com/@nimritakoul01/building-a-bank-support-agent-using-pydanticai-114a04886f9b)  
21. What's the best format to pass data to an LLM for optimal output? : r/PromptEngineering, дата последнего обращения: января 9, 2026, [https://www.reddit.com/r/PromptEngineering/comments/1mb80ra/whats\_the\_best\_format\_to\_pass\_data\_to\_an\_llm\_for/](https://www.reddit.com/r/PromptEngineering/comments/1mb80ra/whats_the_best_format_to_pass_data_to_an_llm_for/)  
22. Data Analyst \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/examples/data-analyst/](https://ai.pydantic.dev/examples/data-analyst/)  
23. Setup \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/examples/setup/](https://ai.pydantic.dev/examples/setup/)  
24. Quantifying The Irrational: How To Create The Best LLM Prompt For Automated Trading Strategies \- Celan Bryant, дата последнего обращения: января 9, 2026, [https://celanbryant.medium.com/quantifying-the-irrational-how-to-create-the-best-llm-prompt-for-automated-trading-strategies-6cde15e0f846](https://celanbryant.medium.com/quantifying-the-irrational-how-to-create-the-best-llm-prompt-for-automated-trading-strategies-6cde15e0f846)  
25. Looking for High-Quality Prompt Ideas for Market Analysis (Crypto \+ Stocks) : r/PromptEngineering \- Reddit, дата последнего обращения: января 9, 2026, [https://www.reddit.com/r/PromptEngineering/comments/1p71vui/looking\_for\_highquality\_prompt\_ideas\_for\_market/](https://www.reddit.com/r/PromptEngineering/comments/1p71vui/looking_for_highquality_prompt_ideas_for_market/)  
26. Chain-of-Thought Prompting | Prompt Engineering Guide, дата последнего обращения: января 9, 2026, [https://www.promptingguide.ai/techniques/cot](https://www.promptingguide.ai/techniques/cot)  
27. Prompting Strategies for Financial Analysis \- Claude Help Center, дата последнего обращения: января 9, 2026, [https://support.claude.com/en/articles/12220277-prompting-strategies-for-financial-analysis](https://support.claude.com/en/articles/12220277-prompting-strategies-for-financial-analysis)  
28. Validators \- Pydantic, дата последнего обращения: января 9, 2026, [https://docs.pydantic.dev/latest/concepts/validators/](https://docs.pydantic.dev/latest/concepts/validators/)  
29. pydantic\_ai.agent \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/api/agent/](https://ai.pydantic.dev/api/agent/)  
30. Dependencies \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/dependencies/](https://ai.pydantic.dev/dependencies/)  
31. Toolsets \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/toolsets/](https://ai.pydantic.dev/toolsets/)  
32. Function Tools \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/tools/](https://ai.pydantic.dev/tools/)  
33. Best strategy on managing concurrent calls ? (Python/Asyncio) \- API, дата последнего обращения: января 9, 2026, [https://community.openai.com/t/best-strategy-on-managing-concurrent-calls-python-asyncio/849702](https://community.openai.com/t/best-strategy-on-managing-concurrent-calls-python-asyncio/849702)  
34. Implementing Effective API Rate Limiting in Python | by PI | Neural Engineer \- Medium, дата последнего обращения: января 9, 2026, [https://medium.com/neural-engineer/implementing-effective-api-rate-limiting-in-python-6147fdd7d516](https://medium.com/neural-engineer/implementing-effective-api-rate-limiting-in-python-6147fdd7d516)  
35. Multi-Agent Patterns \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/multi-agent-applications/](https://ai.pydantic.dev/multi-agent-applications/)  
36. Anthropic \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/models/anthropic/](https://ai.pydantic.dev/models/anthropic/)  
37. pydantic\_ai.output \- Pydantic AI, дата последнего обращения: января 9, 2026, [https://ai.pydantic.dev/api/output/](https://ai.pydantic.dev/api/output/)