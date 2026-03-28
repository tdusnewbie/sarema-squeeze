import ccxt.async_support as ccxt
import logging
from typing import List, Optional

class ExchangeService:
    def __init__(self, default_exchange: str = "binance"):
        self.default_exchange = default_exchange
        self.logger = logging.getLogger(__name__)

    async def search_symbols(self, query: str, exchange_id: Optional[str] = None) -> tuple[str, List[str]]:
        """
        Searches for CCXT symbols matching a TradingView name.
        Returns (exchange_id, list_of_symbols)
        """
        query = query.upper()
        target_exchange = exchange_id or self.default_exchange
        
        if ":" in query and not exchange_id:
            target_exchange, query = query.split(":", 1)
            target_exchange = target_exchange.lower()

        matches = await self._fetch_matches(target_exchange, query)
        
        # Fallback to other exchanges if no specific exchange was requested
        if not matches and not exchange_id and target_exchange == self.default_exchange:
            for alt_ex in ["bybit", "okx", "mexc"]:
                matches = await self._fetch_matches(alt_ex, query)
                if matches:
                    return alt_ex, matches
        
        return target_exchange, matches

    async def _fetch_matches(self, exchange_id: str, query: str) -> List[str]:
        try:
            exchange = getattr(ccxt, exchange_id)()
            markets = await exchange.load_markets()
            symbols = list(markets.keys())

            def normalize(s):
                return s.upper().replace('/', '').replace(':', '').replace('-', '').replace('_', '').replace('.', '')

            nq = normalize(query)
            matches = [s for s in symbols if nq in normalize(s)]

            # Perpetual logic
            is_perp_request = 'PERP' in query or query.endswith('.P') or query.endswith('P')
            if is_perp_request:
                alt_query = query.replace('PERP', '').replace('.P', '')
                if alt_query.endswith('P') and not matches: 
                    alt_query = alt_query[:-1]
                
                nq_alt = normalize(alt_query)
                perp_matches = []
                for s in symbols:
                    m = markets[s]
                    if nq_alt in normalize(s) and (m.get('type') in ['swap', 'future']):
                        perp_matches.append(s)
                
                if perp_matches:
                    await exchange.close()
                    return perp_matches

            await exchange.close()
            return matches
        except Exception as e:
            self.logger.error(f"Error fetching matches from {exchange_id}: {e}")
            return []
