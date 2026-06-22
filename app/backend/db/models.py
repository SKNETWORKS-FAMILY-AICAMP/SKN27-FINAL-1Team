from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship
from app.backend.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    nickname = Column(String(100), nullable=True)
    provider = Column("auth_provider", String(50), nullable=False)
    provider_id = Column("provider_user_id", String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    fridge_items = relationship("FridgeItem", back_populates="user", cascade="all, delete-orphan")
    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    allergies = Column(String, nullable=True)
    disliked_ingredients = Column(String, nullable=True)
    preferred_ingredients = Column(String, nullable=True)
    allow_expiry_alert = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="preference")

class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    normalized_name = Column(String(100), nullable=False, unique=True)
    category = Column(String(100), nullable=True)
    default_unit = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    fridge_items = relationship("FridgeItem", back_populates="ingredient")

class FridgeItem(Base):
    __tablename__ = "fridge_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    import_candidate_id = Column(Integer, unique=True, nullable=True) # ForeignKey 생략 (당장 구현 불필요)
    display_name = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(30), nullable=True)
    storage_location = Column(String(50), nullable=True)
    purchased_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="normal")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="fridge_items")
    ingredient = relationship("Ingredient", back_populates="fridge_items")
