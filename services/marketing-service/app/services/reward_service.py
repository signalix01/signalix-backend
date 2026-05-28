"""
Reward Service
Handles referral reward application and tracking
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RewardService:
    """Service for managing referral rewards"""
    
    def __init__(self):
        self.subscription_service_url = settings.SUBSCRIPTION_SERVICE_URL or "http://localhost:8006"
    
    async def award_referral_rewards(
        self,
        referrer_user_id: str,
        referred_user_id: str,
        referral_id: str,
        conn
    ) -> dict:
        """
        Award rewards for a successful referral conversion
        
        Rewards:
            - Referrer: 1 month free Pro subscription
            - Referred user: 20% discount on first month
        
        Args:
            referrer_user_id: UUID of the user who referred
            referred_user_id: UUID of the user who was referred
            referral_id: UUID of the referral record
            conn: Database connection
            
        Returns:
            dict with reward details
        """
        try:
            # Check if rewards already granted
            existing_rewards = await conn.fetch(
                """
                SELECT id, user_id, reward_type, status
                FROM referral_rewards
                WHERE referral_id = $1
                """,
                referral_id
            )
            
            if existing_rewards:
                logger.warning(f"Rewards already exist for referral {referral_id}")
                return {
                    "success": False,
                    "message": "Rewards already granted for this referral"
                }
            
            # Award referrer reward: 1 month free Pro
            referrer_reward = await self._grant_free_month_pro(
                referrer_user_id,
                referral_id,
                conn
            )
            
            # Award referred user reward: 20% discount on first month
            referred_reward = await self._grant_first_month_discount(
                referred_user_id,
                referral_id,
                conn
            )
            
            # Update referral record
            await conn.execute(
                """
                UPDATE referrals
                SET 
                    referrer_reward_paise = $1,
                    referred_reward_paise = $2,
                    referrer_reward_granted = $3,
                    referred_reward_granted = $4,
                    updated_at = NOW()
                WHERE id = $5
                """,
                referrer_reward['value_paise'],
                referred_reward['value_paise'],
                referrer_reward['granted'],
                referred_reward['granted'],
                referral_id
            )
            
            # Update referrer's total rewards
            await conn.execute(
                """
                UPDATE referrers
                SET 
                    total_rewards_paise = total_rewards_paise + $1,
                    updated_at = NOW()
                WHERE user_id = $2
                """,
                referrer_reward['value_paise'],
                referrer_user_id
            )
            
            logger.info(f"Awarded referral rewards for referral {referral_id}")
            
            return {
                "success": True,
                "referrer_reward": referrer_reward,
                "referred_reward": referred_reward
            }
            
        except Exception as e:
            logger.error(f"Error awarding referral rewards: {str(e)}")
            raise
    
    async def _grant_free_month_pro(
        self,
        user_id: str,
        referral_id: str,
        conn
    ) -> dict:
        """
        Grant 1 month free Pro subscription to referrer
        
        This extends the user's Pro subscription by 1 month or
        grants a 1-month Pro credit if they're not currently Pro.
        """
        try:
            # Pro subscription value: Rs 1,999/month = 199,900 paise
            reward_value_paise = 199900
            expires_at = datetime.utcnow() + timedelta(days=365)  # 1 year expiry
            
            # Create reward record
            reward_id = await conn.fetchval(
                """
                INSERT INTO referral_rewards (
                    referral_id,
                    user_id,
                    reward_type,
                    reward_value_paise,
                    status,
                    expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                referral_id,
                user_id,
                'free_month',
                reward_value_paise,
                'pending',
                expires_at
            )
            
            # Call subscription service to extend subscription
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.subscription_service_url}/api/v1/subscriptions/extend",
                        json={
                            "user_id": user_id,
                            "tier": "pro",
                            "duration_days": 30,
                            "reason": "referral_reward"
                        },
                        timeout=10.0
                    )
                    
                    if response.status_code == 200:
                        # Mark reward as granted
                        await conn.execute(
                            """
                            UPDATE referral_rewards
                            SET status = 'granted', granted_at = NOW()
                            WHERE id = $1
                            """,
                            reward_id
                        )
                        
                        logger.info(f"Granted 1 month free Pro to user {user_id}")
                        
                        return {
                            "reward_id": str(reward_id),
                            "type": "free_month",
                            "value_paise": reward_value_paise,
                            "granted": True
                        }
                    else:
                        logger.error(f"Failed to extend subscription: {response.text}")
                        return {
                            "reward_id": str(reward_id),
                            "type": "free_month",
                            "value_paise": reward_value_paise,
                            "granted": False,
                            "error": "subscription_service_error"
                        }
                        
            except httpx.RequestError as e:
                logger.error(f"Subscription service request failed: {str(e)}")
                return {
                    "reward_id": str(reward_id),
                    "type": "free_month",
                    "value_paise": reward_value_paise,
                    "granted": False,
                    "error": "subscription_service_unavailable"
                }
                
        except Exception as e:
            logger.error(f"Error granting free month Pro: {str(e)}")
            raise
    
    async def _grant_first_month_discount(
        self,
        user_id: str,
        referral_id: str,
        conn
    ) -> dict:
        """
        Grant 20% discount on first month to referred user
        
        This creates a discount coupon that will be applied
        to the user's first subscription payment.
        """
        try:
            # 20% discount on Pro (Rs 1,999) = Rs 400 discount = 40,000 paise
            reward_value_paise = 40000
            expires_at = datetime.utcnow() + timedelta(days=90)  # 90 days to use
            
            # Create reward record
            reward_id = await conn.fetchval(
                """
                INSERT INTO referral_rewards (
                    referral_id,
                    user_id,
                    reward_type,
                    reward_value_paise,
                    status,
                    expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                referral_id,
                user_id,
                'discount',
                reward_value_paise,
                'pending',
                expires_at
            )
            
            # Call subscription service to create discount coupon
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.subscription_service_url}/api/v1/coupons/create",
                        json={
                            "user_id": user_id,
                            "discount_percent": 20,
                            "max_redemptions": 1,
                            "duration": "once",
                            "reason": "referral_reward"
                        },
                        timeout=10.0
                    )
                    
                    if response.status_code == 200:
                        # Mark reward as granted
                        await conn.execute(
                            """
                            UPDATE referral_rewards
                            SET status = 'granted', granted_at = NOW()
                            WHERE id = $1
                            """,
                            reward_id
                        )
                        
                        logger.info(f"Granted 20% discount to user {user_id}")
                        
                        return {
                            "reward_id": str(reward_id),
                            "type": "discount",
                            "value_paise": reward_value_paise,
                            "granted": True
                        }
                    else:
                        logger.error(f"Failed to create discount coupon: {response.text}")
                        return {
                            "reward_id": str(reward_id),
                            "type": "discount",
                            "value_paise": reward_value_paise,
                            "granted": False,
                            "error": "subscription_service_error"
                        }
                        
            except httpx.RequestError as e:
                logger.error(f"Subscription service request failed: {str(e)}")
                return {
                    "reward_id": str(reward_id),
                    "type": "discount",
                    "value_paise": reward_value_paise,
                    "granted": False,
                    "error": "subscription_service_unavailable"
                }
                
        except Exception as e:
            logger.error(f"Error granting first month discount: {str(e)}")
            raise
    
    async def get_user_rewards(self, user_id: str, conn) -> list:
        """
        Get all rewards for a user
        
        Args:
            user_id: User UUID
            conn: Database connection
            
        Returns:
            List of reward records
        """
        try:
            rewards = await conn.fetch(
                """
                SELECT 
                    rr.id,
                    rr.reward_type,
                    rr.reward_value_paise,
                    rr.status,
                    rr.granted_at,
                    rr.expires_at,
                    rr.created_at,
                    r.referred_user_id
                FROM referral_rewards rr
                JOIN referrals r ON rr.referral_id = r.id
                WHERE rr.user_id = $1
                ORDER BY rr.created_at DESC
                """,
                user_id
            )
            
            return [dict(reward) for reward in rewards]
            
        except Exception as e:
            logger.error(f"Error fetching user rewards: {str(e)}")
            raise


# Singleton instance
reward_service = RewardService()
