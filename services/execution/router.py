from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from shared.database.session import get_db
from shared.database.execution_models import Order, OrderType, OrderSide, OrderStatus
from shared.database.user_models import User
from shared.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/execution/orders", tags=["execution"])

class CreateOrderRequest(BaseModel):
    instrument: str
    orderType: OrderType
    side: OrderSide
    quantity: float
    price: Optional[float] = None
    signalId: Optional[str] = None

@router.get("", response_model=List[dict])
async def get_orders(
    status: Optional[str] = None,
    instrument: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Order).where(Order.user_id == current_user.id)
    
    if status:
        try:
            query = query.where(Order.status == OrderStatus(status))
        except ValueError:
            pass
            
    if instrument:
        query = query.where(Order.instrument == instrument)
        
    query = query.order_by(desc(Order.timestamp)).limit(limit)
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return [order.to_dict() for order in orders]

@router.post("", response_model=dict)
async def create_order(
    req: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_order = Order(
        user_id=current_user.id,
        instrument=req.instrument,
        orderType=req.orderType,
        side=req.side,
        quantity=req.quantity,
        price=req.price,
        signalId=req.signalId,
        status=OrderStatus.PENDING
    )
    
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    
    return new_order.to_dict()

@router.delete("/{order_id}", response_model=dict)
async def cancel_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Order).where(Order.id == order_id, Order.user_id == current_user.id))
    order = result.scalars().first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel order with status {order.status}")
        
    order.status = OrderStatus.CANCELLED
    await db.commit()
    await db.refresh(order)
    
    return {
        "success": True,
        "message": "Order cancelled successfully",
        "order": order.to_dict()
    }
