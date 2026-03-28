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
        Returns (exchange_id, list_of_formatted_strings)
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
            
            def normalize(s):
                return s.upper().replace('/', '').replace(':', '').replace('-', '').replace('_', '').replace('.', '')

            nq = normalize(query)
            
            # Find matching symbols and include their type
            results = []
            is_perp_request = 'PERP' in query or query.endswith('.P') or query.endswith('P')
            alt_query = query.replace('PERP', '').replace('.P', '')
            if alt_query.endswith('P') and 'PERP' not in query: 
                alt_query = alt_query[:-1]
            nq_alt = normalize(alt_query)

            for symbol, m in markets.items():
                m_type = m.get('type', 'unknown').upper()
                norm_symbol = normalize(symbol)
                
                # If user asked for PERP, prioritize swaps/futures
                if is_perp_request:
                    if nq_alt in norm_symbol and m.get('type') in ['swap', 'future']:
                        results.append(f"{symbol} ({m_type})")
                else:
                    if nq in norm_symbol:
                        results.append(f"{symbol} ({m_type})")

            await exchange.close()
            return results
        except Exception as e:
            self.logger.error(f"Error fetching matches from {exchange_id}: {e}")
            return []
