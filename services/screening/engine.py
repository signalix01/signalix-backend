"""
AI Screening Engine Orchestrator

This module orchestrates all 3 layers of the screening pipeline:
1. SQL pre-filter (< 500ms for 10K instruments)
2. TA-Lib scoring (< 10 seconds for 200 instruments)
3. AI scoring (< 30 seconds for top 50 candidates)

Requirements: 9.1, 9.5, 9.6, 9.7
"""
import logging
import time
import uuid
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from services.screening.models import ScreeningCriteria, ScreeningResult, ScreenedInstrument
from services.screening.sql_filter import SQLPreFilter
from services.screening.ta_scorer import TAScorer
from services.screening.ai_scorer import AIScorer

logger = logging.getLogger(__name__)


class AIScreeningEngine:
    """
    Multi-layer AI screening engine orchestrator
    
    Orchestrates the 3-layer screening pipeline:
    - Layer 1: SQL pre-filter from TimescaleDB materialized view
    - Layer 2: TA-Lib scoring on passed instruments
    - Layer 3: AI scoring on top 50 candidates
    
    Performance targets:
    - Layer 1: < 500ms for 10,000 instruments
    - Layer 2: < 10 seconds for 200 instruments
    - Layer 3: < 30 seconds for 50 instruments
    - Total: < 45 seconds end-to-end
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize screening engine
        
        Args:
            session: Async database session
        """
        self.session = session
        self.sql_filter = SQLPreFilter(session)
        self.ta_scorer = TAScorer(session)
        self.ai_scorer = AIScorer()
    
    async def run_screening(
        self,
        criteria: ScreeningCriteria,
        universe: List[str]
    ) -> ScreeningResult:
        """
        Run complete 3-layer screening pipeline
        
        Pipeline flow:
        1. SQL pre-filter: Filter universe down to ~200 symbols
        2. TA-Lib scoring: Score filtered symbols, get top 50
        3. AI scoring: Get AI signals for top 50 (if min_ai_confidence set)
        
        Args:
            criteria: Screening criteria with all filter parameters
            universe: List of symbols to screen (e.g., NSE 100, all crypto)
            
        Returns:
            ScreeningResult with top instruments that passed all layers
            
        Raises:
            Exception: If any layer fails critically
        """
        start_time = time.time()
        screening_id = str(uuid.uuid4())
        
        logger.info(
            f"Screening started",
            extra={
                "screening_id": screening_id,
                "criteria_name": criteria.name,
                "universe_size": len(universe),
                "asset_classes": criteria.asset_class
            }
        )
        
        try:
            # Layer 1: SQL pre-filter
            logger.info(f"Layer 1: SQL pre-filter starting")
            layer1_start = time.time()
            
            sql_filtered_symbols = await self.sql_filter.filter(criteria, universe)
            
            layer1_duration = time.time() - layer1_start
            logger.info(
                f"Layer 1: SQL pre-filter completed",
                extra={
                    "screening_id": screening_id,
                    "duration_ms": int(layer1_duration * 1000),
                    "input_count": len(universe),
                    "output_count": len(sql_filtered_symbols)
                }
            )
            
            if not sql_filtered_symbols:
                logger.warning(
                    f"No instruments passed SQL pre-filter",
                    extra={
                        "screening_id": screening_id,
                        "criteria_name": criteria.name
                    }
                )
                return ScreeningResult(
                    screening_id=screening_id,
                    criteria_name=criteria.name,
                    run_at=datetime.utcnow().isoformat(),
                    duration_seconds=time.time() - start_time,
                    instruments_scanned=len(universe),
                    instruments_passed=0,
                    results=[]
                )
            
            # Layer 2: TA-Lib scoring
            logger.info(f"Layer 2: TA-Lib scoring starting")
            layer2_start = time.time()
            
            scored_instruments = await self.ta_scorer.score(sql_filtered_symbols, criteria)
            
            layer2_duration = time.time() - layer2_start
            logger.info(
                f"Layer 2: TA-Lib scoring completed",
                extra={
                    "screening_id": screening_id,
                    "duration_seconds": round(layer2_duration, 2),
                    "input_count": len(sql_filtered_symbols),
                    "output_count": len(scored_instruments)
                }
            )
            
            if not scored_instruments:
                logger.warning(
                    f"No instruments passed TA-Lib scoring",
                    extra={
                        "screening_id": screening_id,
                        "criteria_name": criteria.name
                    }
                )
                return ScreeningResult(
                    screening_id=screening_id,
                    criteria_name=criteria.name,
                    run_at=datetime.utcnow().isoformat(),
                    duration_seconds=time.time() - start_time,
                    instruments_scanned=len(universe),
                    instruments_passed=0,
                    results=[]
                )
            
            # Get top 50 candidates for AI layer
            top_candidates = sorted(scored_instruments, key=lambda x: x.score, reverse=True)[:50]
            
            # Layer 3: AI scoring (if min_ai_confidence is set)
            if criteria.min_ai_confidence is not None:
                logger.info(f"Layer 3: AI scoring starting")
                layer3_start = time.time()
                
                ai_scored_instruments = await self.ai_scorer.score(top_candidates, criteria)
                
                layer3_duration = time.time() - layer3_start
                logger.info(
                    f"Layer 3: AI scoring completed",
                    extra={
                        "screening_id": screening_id,
                        "duration_seconds": round(layer3_duration, 2),
                        "input_count": len(top_candidates),
                        "output_count": len(ai_scored_instruments)
                    }
                )
                
                # Filter by AI confidence and direction
                final_results = []
                for inst in ai_scored_instruments:
                    # Check AI confidence threshold
                    if inst.ai_confidence is None or inst.ai_confidence < criteria.min_ai_confidence:
                        continue
                    
                    # Check AI direction filter
                    if criteria.ai_direction_filter is not None and criteria.ai_direction_filter != "either":
                        if inst.ai_signal != criteria.ai_direction_filter:
                            continue
                    
                    final_results.append(inst)
                
                # Sort by AI confidence descending
                final_results.sort(key=lambda x: x.ai_confidence or 0, reverse=True)
                
            else:
                # No AI layer - use TA-scored results
                final_results = top_candidates
            
            # Return top 20 results
            final_results = final_results[:20]
            
            total_duration = time.time() - start_time
            
            logger.info(
                f"Screening completed successfully",
                extra={
                    "screening_id": screening_id,
                    "criteria_name": criteria.name,
                    "total_duration_seconds": round(total_duration, 2),
                    "instruments_scanned": len(universe),
                    "instruments_passed": len(final_results),
                    "layer1_duration_ms": int(layer1_duration * 1000),
                    "layer2_duration_seconds": round(layer2_duration, 2),
                    "layer3_duration_seconds": round(layer3_duration, 2) if criteria.min_ai_confidence else 0
                }
            )
            
            return ScreeningResult(
                screening_id=screening_id,
                criteria_name=criteria.name,
                run_at=datetime.utcnow().isoformat(),
                duration_seconds=round(total_duration, 2),
                instruments_scanned=len(universe),
                instruments_passed=len(final_results),
                results=final_results
            )
            
        except Exception as e:
            total_duration = time.time() - start_time
            logger.error(
                f"Screening failed",
                extra={
                    "screening_id": screening_id,
                    "criteria_name": criteria.name,
                    "duration_seconds": round(total_duration, 2),
                    "error": str(e)
                }
            )
            raise Exception(f"Screening failed: {str(e)}")
    
    async def get_default_universe(self, asset_classes: List[str]) -> List[str]:
        """
        Get default universe of symbols for given asset classes
        
        This is a helper method to get a reasonable default universe
        when the user doesn't specify one.
        
        Args:
            asset_classes: List of asset classes (equity, fo, crypto, forex, commodity)
            
        Returns:
            List of symbols for the given asset classes
        """
        from sqlalchemy import text
        
        try:
            # Build query to get active instruments for asset classes
            query = text("""
                SELECT DISTINCT symbol 
                FROM instruments 
                WHERE asset_class = ANY(:asset_classes)
                  AND is_active = true
                ORDER BY symbol
                LIMIT 1000
            """)
            
            result = await self.session.execute(query, {"asset_classes": asset_classes})
            rows = result.fetchall()
            symbols = [row[0] for row in rows]
            
            logger.info(
                f"Default universe fetched",
                extra={
                    "asset_classes": asset_classes,
                    "symbol_count": len(symbols)
                }
            )
            
            return symbols
            
        except Exception as e:
            logger.error(f"Failed to fetch default universe: {str(e)}")
            # Return empty list on error - caller should handle
            return []
