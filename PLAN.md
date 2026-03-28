# TradingView Indicator Alert Bot Plan

## 1. Trading Requirements (The Logic)

### Objective
Create a 100% self-hosted automated system that monitors technical indicators and triggers actions (like sending a Telegram notification) when all specified conditions align perfectly.

### CORE RULE: THE "HARD" CONDITION
The bot uses a strict "4-out-of-4" logical group check. For an alert to fire, **all groups must be True on the same candle.**

*   **Logical Groups:**
    1.  **PSAR Flip:** Dot jumps from above to below (Long) or below to above (Short) relative to the candle.
    2.  **EMA Alignment:** EMA 5 > 9 > 100 (Long) or EMA 5 < 9 < 100 (Short).
    3.  **Price Action:** Candle MUST be Green (Long) or Red (Short) AND must pierce the PSAR level.
    4.  **Squeeze Momentum:** Histogram bar must be Light Green (Long) or Light Red (Short).

### SOFT CONDITION: SEQUENTIAL CONFIRMATION
To catch more opportunities, the bot uses a "Watch Window" logic:
1. **The Setup:** Entry into Watch Mode requires:
    *   **PSAR Flip** group MUST be True.
    *   **At least 2 of the other 3 groups** (EMA, Price Action, Squeeze) must be True.
2. **The Lock:** When entering Watch Mode, the bot **locks the PSAR level** (the "coordinator") from the setup candle.
3. **The Window:** The bot monitors the next **5 candles**.
4. **The Completion:** A Sequential Signal fires if the **missing groups** from the setup become True within the window. **Crucially**, the Price Action group is checked against the **Locked PSAR level**.

---

## 2. Technical Architecture (Layered Edition)

### Core Mandate: Clean Code Strategy
*   **Service Layer (`src/services`):** Isolated business logic for Indicators, Strategy, Exchange interaction, and Scanner management.
*   **Data Layer (`src/data`):** DuckDB persistence and watchlist management.
*   **Interface Layer:** Telegram Bot (Interactive) and Typer CLI (Backtesting/Manual).

### Core Application
*   **Language:** Python 3.12+
*   **Package Manager:** `uv`.
*   **Telegram Library:** `python-telegram-bot` (to handle incoming commands like /add, /search).
*   **Concurrency:** `asyncio` to run multiple scanners in parallel.

### Data & Processing
*   **Database:** **DuckDB** (For storage and watchlist management).
*   **Processing:** **Pandas** + **TA-Lib**.

---

## 3. Implementation Phases

### Phase 1: Project Initialization & Logic Verification (COMPLETED ✅)
1. Initialize project with `uv`.
2. Implement and test Indicators and Strategy.
3. Successfully scanned live data and verified signals.

### Phase 2: Interactive Telegram Command Center (COMPLETED ✅)
1. **Command Handler:** Implement `/add`, `/remove`, `/list` to manage the watchlist.
2. **Search Utility:** Implement `/search` to map TradingView names (e.g., BTCUSDTPERP) to CCXT symbols.
3. **Persistence:** Save the watchlist to DuckDB.
4. **Multi-Runner:** Build a manager that starts/stops `LiveRunner` tasks dynamically.
5. **Clean Code Refactor:** Moved logic into dedicated services and added unit tests for core functionality.

### Phase 3: Deployment (IN PROGRESS ⏳)
1. Write Dockerfile.
2. Create k3s manifests.
3. Deploy to your cluster!

### Phase 4: Optimization & Scaling (FUTURE 🚀)
1. **Caching:** Cache exchange market data to speed up `/search`.
2. **Web Dashboard:** Simple visualization of active scanners.
3. **Advanced Risk Management:** Add SL/TP calculation suggestions in notifications.
