from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Date, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship
from app.backend.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=True)
    provider = Column(String, nullable=False)  # kakao, naver, google
    provider_id = Column(String, unique=True, index=True, nullable=False)
    nickname = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    onboarding = relationship("UserOnboarding", back_populates="user", uselist=False, cascade="all, delete-orphan")
    fridges = relationship("Fridge", back_populates="user", cascade="all, delete-orphan")


class UserOnboarding(Base):
    __tablename__ = "user_onboarding"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    allergy = Column(String, nullable=True)
    disliked_ingredients = Column(String, nullable=True)
    is_alert_allowed = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="onboarding")


class Fridge(Base):
    __tablename__ = "fridges"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False, default="나의 냉장고")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="fridges")
    ingredients = relationship("Ingredient", back_populates="fridge", cascade="all, delete-orphan")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    fridge_id = Column(BigInteger, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True)
    quantity = Column(Numeric(precision=10, scale=2), default=1.0, nullable=False)
    unit = Column(String, nullable=False, default="개")  # 개, g, ml 등
    storage_method = Column(String, nullable=False, default="냉장")  # 냉장, 냉동, 실온
    purchase_date = Column(Date, server_default=func.current_date(), nullable=False)
    expiration_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    fridge = relationship("Fridge", back_populates="ingredients")
