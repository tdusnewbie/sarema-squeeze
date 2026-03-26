# TradingView Indicator Alert Bot Plan

## 1. Trading Requirements (The Logic)

### Objective
Create a 100% self-hosted automated system that monitors technical indicators and triggers actions (like sending a Telegram notification) when all specified conditions align perfectly.

### CORE RULE: THE "HARD" CONDITION
The bot uses a strict "5-out-of-5" logic. For an alert to fire, **all 5 conditions must be True on the same candle.**

*   **LONG:**
    *   **EMA Alignment:** EMA 5 > EMA 9 > EMA 100.
    *   **PSAR Flip:** Dot jumps from above to below the candle (Bullish Flip).
    *   **Candle Color:** **MUST be Green** (`Close > Open`).
    *   **Price Action:** The candle must "go through" the previous PSAR level (`Low < PSAR[1]` AND `Close > PSAR[1]`).
    *   **Squeeze Momentum:** Histogram bar must be **Light Green** (Momentum > 0 and increasing).

*   **SHORT:**
    *   **EMA Alignment:** EMA 5 < EMA 9 < EMA 100.
    *   **PSAR Flip:** Dot jumps from below to above the candle (Bearish Flip).
    *   **Candle Color:** **MUST be Red** (`Close < Open`).
    *   **Price Action:** The candle must "go through" the previous PSAR level (`High > PSAR[1]` AND `Close < PSAR[1]`).
    *   **Squeeze Momentum:** Histogram bar must be **Light Red** (Momentum < 0 and getting more negative).

### SOFT CONDITION: SEQUENTIAL CONFIRMATION
To catch more opportunities, the bot uses a "Watch Window" logic:
1. **The Setup:** If **3 out of the 4** main indicators (EMA, PSAR, Candle Color, Squeeze) align, the bot enters "Watch Mode."
2. **The Window:** The bot will monitor the next **5 candles** specifically looking for the full **Hard Condition (5/5)** to complete.
3. **The Trigger:** If 5/5 matches during this window, the alert fires immediately.
4. **The Reset:** If the window closes (5 candles pass) without a 5/5 match, the bot resets and starts a fresh check on the next candle.

---

## 2. Technical Architecture (Interactive Edition)

### Core Mandate: Clean Code Strategy
*   **Layered Architecture:** Data (DuckDB), Engine (Indicators), Notifier (Telegram), Multi-Runner (Manager).
*   **Persistence:** Use DuckDB to store `watchlist` (exchange, symbol, timeframe).

### Core Application
*   **Language:** Python 3.12+
*   **Package Manager:** `uv`.
*   **Telegram Library:** `python-telegram-bot` (to handle incoming commands like /add).
*   **Concurrency:** `asyncio` to run multiple scanners in parallel within one container.

### Data & Processing
*   **Database:** **DuckDB** (For storage and watchlist management).
*   **Processing:** **Polars** + **TA-Lib**.

### Containerization & Deployment
*   **Container:** **Standard Dockerfile**.
*   **Cluster:** **k3s Cluster**.

---

## 3. Implementation Phases

### Phase 1: Project Initialization & Logic Verification (COMPLETED ✅)
1. Initialize project with `uv`.
2. Implement and test Indicators and Strategy.
3. Successfully scanned live data and verified signals.

### Phase 2: Interactive Telegram Command Center
1. **Command Handler:** Implement `/add`, `/remove`, `/list` to manage the watchlist.
2. **Persistence:** Save the watchlist to DuckDB.
3. **Multi-Runner:** Build a manager that starts/stops `LiveRunner` tasks dynamically when you add/remove pairs via Telegram.

### Phase 3: Deployment
1. Write Dockerfile.
2. Create k3s manifests.
3. Deploy to your cluster!
