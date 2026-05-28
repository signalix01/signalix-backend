"""
SQL Pre-Filter Layer for AI Screening Engine

This module implements the first layer of the screening pipeline:
fast SQL-based filtering against the screening_snapshot materialized view.

Requirements: 9.2
"""
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import asyncio

from services.screening.models import ScreeningCriteria

logger = logging.getLogger(__name__)


class SQLPreFilter:
    """
    SQL-based pre-filter for screening engine
    
    Queries the screening_snapshot materialized view to quickly filter
    thousands of instruments down to a manageable set (up to 200) that
    pass basic criteria.
    
    Performance target: < 500ms for 10,000 instruments
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize SQL pre-filter
        
        Args:
            session: Async database session
        """
        self.session = session
    
    async def filter(
        self,
        criteria: ScreeningCriteria,
        universe: List[str]
    ) -> List[str]:
        """
        Filter universe of symbols using SQL against screening_snapshot
        
        Builds a dynamic parameterized SQL query based on non-null criteria fields.
        Returns up to 200 symbols that pass all filters.
        
        Args:
            criteria: Screening criteria with filter parameters
            universe: List of symbols to screen (e.g., NSE 100, all crypto)
            
        Returns:
            List of symbols that passed SQL filters (max 200)
            
        Raises:
            asyncio.TimeoutError: If query exceeds 5-second timeout
            Exception: If database query fails
        """
        if not universe:
            logger.warning("Empty universe provided to SQL pre-filter")
            return []
        
        # Build dynamic SQL query
        conditions = []
        params = {"universe": universe}
        
        # Always filter by universe
        conditions.append("symbol = ANY(:universe)")
        
        # Technical filters (all markets)
        if criteria.min_rsi is not None:
            conditions.append("rsi_14 >= :min_rsi")
            params["min_rsi"] = criteria.min_rsi
        
        if criteria.max_rsi is not None:
            conditions.append("rsi_14 <= :max_rsi")
            params["max_rsi"] = criteria.max_rsi
        
        if criteria.require_above_ema is not None:
            # Check if price is above the specified EMA
            ema_column = f"ema_{criteria.require_above_ema}"
            conditions.append(f"close > {ema_column}")
        
        if criteria.min_adx is not None:
            conditions.append("adx_14 >= :min_adx")
            params["min_adx"] = criteria.min_adx
        
        if criteria.min_volume_ratio is not None:
            conditions.append("volume_ratio >= :min_volume_ratio")
            params["min_volume_ratio"] = criteria.min_volume_ratio
        
        if criteria.price_breakout_days is not None:
            # Check if current price is at X-day high
            # This requires comparing close to highest_high_X column
            breakout_column = f"highest_high_{criteria.price_breakout_days}"
            conditions.append(f"close >= {breakout_column}")
        
        # Options-specific filters (F&O)
        if criteria.min_iv_rank is not None:
            conditions.append("iv_rank >= :min_iv_rank")
            params["min_iv_rank"] = criteria.min_iv_rank
        
        if criteria.max_iv_rank is not None:
            conditions.append("iv_rank <= :max_iv_rank")
            params["max_iv_rank"] = criteria.max_iv_rank
        
        if criteria.min_pcr is not None:
            conditions.append("pcr >= :min_pcr")
            params["min_pcr"] = criteria.min_pcr
        
        if criteria.max_pcr is not None:
            conditions.append("pcr <= :max_pcr")
            params["max_pcr"] = criteria.max_pcr
        
        # Fundamental filters (equity only)
        if criteria.min_market_cap_cr is not None:
            conditions.append("market_cap_cr >= :min_market_cap_cr")
            params["min_market_cap_cr"] = criteria.min_market_cap_cr
        
        if criteria.max_pe_ratio is not None:
            conditions.append("pe_ratio <= :max_pe_ratio")
            params["max_pe_ratio"] = criteria.max_pe_ratio
        
        if criteria.min_roe_pct is not None:
            conditions.append("roe_pct >= :min_roe_pct")
            params["min_roe_pct"] = criteria.min_roe_pct
        
        if criteria.min_revenue_growth_pct is not None:
            conditions.append("revenue_growth_pct >= :min_revenue_growth_pct")
            params["min_revenue_growth_pct"] = criteria.min_revenue_growth_pct
        
        if criteria.min_promoter_holding_pct is not None:
            conditions.append("promoter_holding_pct >= :min_promoter_holding_pct")
            params["min_promoter_holding_pct"] = criteria.min_promoter_holding_pct
        
        # Crypto-specific filters
        if criteria.min_fear_greed is not None:
            conditions.append("fear_greed_index >= :min_fear_greed")
            params["min_fear_greed"] = criteria.min_fear_greed
        
        if criteria.max_funding_rate is not None:
            conditions.append("funding_rate <= :max_funding_rate")
            params["max_funding_rate"] = criteria.max_funding_rate
        
        if criteria.min_on_chain_netflow_btc is not None:
            conditions.append("on_chain_netflow_btc >= :min_on_chain_netflow_btc")
            params["min_on_chain_netflow_btc"] = criteria.min_on_chain_netflow_btc
        
        # Build final query
        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT symbol 
            FROM screening_snapshot 
            WHERE {where_clause}
            ORDER BY composite_score DESC
            LIMIT 200
        """)
        
        logger.info(
            f"SQL pre-filter query built",
            extra={
                "criteria_name": criteria.name,
                "universe_size": len(universe),
                "num_conditions": len(conditions),
                "has_rsi_filter": criteria.min_rsi is not None or criteria.max_rsi is not None,
                "has_ema_filter": criteria.require_above_ema is not None,
                "has_adx_filter": criteria.min_adx is not None,
                "has_volume_filter": criteria.min_volume_ratio is not None
            }
        )
        
        try:
            # Execute query with 5-second timeout
            result = await asyncio.wait_for(
                self.session.execute(query, params),
                timeout=5.0
            )
            
            # Extract symbols from result
            rows = result.fetchall()
            symbols = [row[0] for row in rows]
            
            logger.info(
                f"SQL pre-filter completed",
                extra={
                    "criteria_name": criteria.name,
                    "input_universe_size": len(universe),
                    "output_symbols_count": len(symbols),
                    "filter_ratio": f"{len(symbols)/len(universe)*100:.1f}%"
                }
            )
            
            return symbols
            
        except asyncio.TimeoutError:
            logger.error(
                f"SQL pre-filter timeout exceeded",
                extra={
                    "criteria_name": criteria.name,
                    "universe_size": len(universe),
                    "timeout_seconds": 5.0
                }
            )
            raise asyncio.TimeoutError(
                f"SQL pre-filter query exceeded 5-second timeout for criteria '{criteria.name}'"
            )
        
        except Exception as e:
            logger.error(
                f"SQL pre-filter query failed",
                extra={
                    "criteria_name": criteria.name,
                    "universe_size": len(universe),
                    "error": str(e)
                }
            )
            raise Exception(f"SQL pre-filter failed: {str(e)}")
    
    async def get_available_columns(self) -> List[str]:
        """
        Get list of available columns in screening_snapshot view
        
        Useful for debugging and validation.
        
        Returns:
            List of column names in screening_snapshot
        """
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'screening_snapshot'
            ORDER BY ordinal_position
        """)
        
        try:
            result = await self.session.execute(query)
            rows = result.fetchall()
            columns = [row[0] for row in rows]
            return columns
        except Exception as e:
            logger.error(f"Failed to get screening_snapshot columns: {str(e)}")
            return []
    
    async def get_snapshot_stats(self) -> dict:
        """
        Get statistics about the screening_snapshot view
        
        Returns:
            Dictionary with snapshot statistics:
            - total_symbols: Total number of symbols in snapshot
            - last_refresh: Last refresh timestamp (if available)
            - symbols_by_exchange: Count by exchange
        """
        try:
            # Get total count
            count_query = text("SELECT COUNT(*) FROM screening_snapshot")
            count_result = await self.session.execute(count_query)
            total_symbols = count_result.scalar()
            
            # Get count by exchange (if exchange column exists)
            exchange_query = text("""
                SELECT exchange, COUNT(*) as count 
                FROM screening_snapshot 
                GROUP BY exchange 
                ORDER BY count DESC
            """)
            
            try:
                exchange_result = await self.session.execute(exchange_query)
                exchange_rows = exchange_result.fetchall()
                symbols_by_exchange = {row[0]: row[1] for row in exchange_rows}
            except Exception:
                # Exchange column might not exist
                symbols_by_exchange = {}
            
            return {
                "total_symbols": total_symbols,
                "symbols_by_exchange": symbols_by_exchange
            }
            
        except Exception as e:
            logger.error(f"Failed to get snapshot stats: {str(e)}")
            return {
                "total_symbols": 0,
                "symbols_by_exchange": {},
                "error": str(e)
            }
