"""
User Management Router for AITBC
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import Session, select
import uuid
import time
import hashlib
from datetime import datetime, timedelta

from ..deps import get_session
from ..domain import User, Wallet
from ..schemas import UserCreate, UserLogin, UserProfile, UserBalance

router = APIRouter(tags=["users"])

# In-memory session storage for demo (use Redis in production)
user_sessions: Dict[str, Dict] = {}

def create_session_token(user_id: str) -> str:
    """Create a session token for a user"""
    token_data = f"{user_id}:{int(time.time())}"
    token = hashlib.sha256(token_data.encode()).hexdigest()
    
    # Store session
    user_sessions[token] = {
        "user_id": user_id,
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + 86400  # 24 hours
    }
    
    return token

def verify_session_token(token: str) -> Optional[str]:
    """Verify a session token and return user_id"""
    if token not in user_sessions:
        return None
    
    session = user_sessions[token]
    
    # Check if expired
    if int(time.time()) > session["expires_at"]:
        del user_sessions[token]
        return None
    
    return session["user_id"]

@router.post("/register", response_model=UserProfile)
async def register_user(
    user_data: UserCreate,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Register a new user"""
    
    # Check if user already exists
    existing_user = session.exec(
        select(User).where(User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        username=user_data.username,
        created_at=datetime.utcnow(),
        last_login=datetime.utcnow()
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # Create wallet for user
    wallet = Wallet(
        user_id=user.id,
        address=f"aitbc_{user.id[:8]}",
        balance=0.0,
        created_at=datetime.utcnow()
    )
    
    session.add(wallet)
    session.commit()
    
    # Create session token
    token = create_session_token(user.id)
    
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": token
    }

@router.post("/login", response_model=UserProfile)
async def login_user(
    login_data: UserLogin,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Login user with wallet address"""
    
    # For demo, we'll create or get user by wallet address
    # In production, implement proper authentication
    
    # Find user by wallet address
    wallet = session.exec(
        select(Wallet).where(Wallet.address == login_data.wallet_address)
    ).first()
    
    if not wallet:
        # Create new user for wallet
        user = User(
            id=str(uuid.uuid4()),
            email=f"{login_data.wallet_address}@aitbc.local",
            username=f"user_{login_data.wallet_address[-8:]}_{str(uuid.uuid4())[:8]}",
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow()
        )
        
        session.add(user)
        session.commit()
        session.refresh(user)
        
        # Create wallet
        wallet = Wallet(
            user_id=user.id,
            address=login_data.wallet_address,
            balance=0.0,
            created_at=datetime.utcnow()
        )
        
        session.add(wallet)
        session.commit()
    else:
        # Update last login
        user = session.exec(
            select(User).where(User.id == wallet.user_id)
        ).first()
        user.last_login = datetime.utcnow()
        session.commit()
    
    # Create session token
    token = create_session_token(user.id)
    
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": token
    }

@router.get("/users/me", response_model=UserProfile)
async def get_current_user(
    token: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get current user profile"""
    
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "session_token": token
    }

@router.get("/users/{user_id}/balance", response_model=UserBalance)
async def get_user_balance(
    user_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get user's AITBC balance"""
    
    wallet = session.exec(
        select(Wallet).where(Wallet.user_id == user_id)
    ).first()
    
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found"
        )
    
    return {
        "user_id": user_id,
        "address": wallet.address,
        "balance": wallet.balance,
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None
    }

@router.post("/logout")
async def logout_user(token: str) -> Dict[str, str]:
    """Logout user and invalidate session"""
    
    if token in user_sessions:
        del user_sessions[token]
    
    return {"message": "Logged out successfully"}

@router.get("/users/{user_id}/transactions")
async def get_user_transactions(
    user_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get user's transaction history"""
    
    # For demo, return empty list
    # In production, query from transaction table
    return {
        "user_id": user_id,
        "transactions": [],
        "total": 0
    }
