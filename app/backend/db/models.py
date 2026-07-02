from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.backend.db.base import Base


# 모든 주요 테이블에서 공통으로 사용하는 BIGINT 기본키 타입입니다.
BigIntPrimaryKey = BigInteger


class User(Base):
    """사용자 테이블을 표현하는 ORM 모델입니다."""

    __tablename__ = "users"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    nickname = Column(String(100), nullable=False)
    provider = Column("auth_provider", String(50), nullable=True)
    provider_id = Column("provider_user_id", String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 사용자와 연결된 하위 도메인 데이터를 ORM 관계로 조회합니다.
    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")
    fridge_items = relationship("FridgeItem", back_populates="user", cascade="all, delete-orphan")
    recommendation_results = relationship("RecommendationResult", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    calendar_integrations = relationship("CalendarIntegration", back_populates="user", cascade="all, delete-orphan")
    calendar_event_logs = relationship("CalendarEventLog", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_onboarded(self) -> bool:
        """사용자 선호 설정 저장 여부로 온보딩 완료 상태를 반환합니다."""
        return self.preference is not None

class UserPreference(Base):
    """사용자별 식재료 선호/알림 설정을 표현하는 ORM 모델입니다."""

    __tablename__ = "user_preferences"
    __table_args__ = (Index("idx_user_preferences_user_id", "user_id"),)

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    allergies = Column(Text, nullable=True)
    disliked_ingredients = Column(Text, nullable=True)
    preferred_ingredients = Column(Text, nullable=True)
    allow_expiry_alert = Column(Boolean, nullable=False, server_default=true())

    # 설정 레코드가 소속된 사용자를 연결합니다.
    user = relationship("User", back_populates="preference")


# Google Calendar 연동 토큰과 캘린더 ID를 사용자별로 저장한다.
class CalendarIntegration(Base):
    """사용자별 외부 캘린더 연동 토큰을 저장합니다."""

    __tablename__ = "calendar_integrations"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_calendar_integrations_user_provider"),
        Index("idx_calendar_integrations_user_id", "user_id"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False, server_default="google")
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    calendar_id = Column(String(255), nullable=False, server_default="primary")
    connected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="calendar_integrations")


# 캘린더 이벤트 생성/수정/중복/실패 결과를 기록한다.
class CalendarEventLog(Base):
    """Google Calendar event sync history."""

    __tablename__ = "calendar_event_logs"
    __table_args__ = (
        Index("idx_calendar_event_logs_user_id", "user_id"),
        Index("idx_calendar_event_logs_created_at", "created_at"),
        Index("idx_calendar_event_logs_event_key", "event_key"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_key = Column(String(255), nullable=False)
    event_type = Column(String(50), nullable=True)
    summary = Column(String(255), nullable=True)
    target_date = Column(Date, nullable=True)
    google_event_id = Column(String(255), nullable=True)
    html_link = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False)
    source = Column(String(30), nullable=False, server_default="manual")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="calendar_event_logs")


class Ingredient(Base):
    """식재료 마스터 테이블을 표현하는 ORM 모델입니다."""

    __tablename__ = "ingredients"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    normalized_name = Column(String(100), nullable=False, unique=True)
    category = Column(String(100), nullable=True)
    default_unit = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 식재료와 연결된 별칭, 영수증 항목, 냉장고 항목, 레시피 데이터를 조회합니다.
    aliases = relationship("IngredientAlias", back_populates="ingredient", cascade="all, delete-orphan")
    receipt_items = relationship("ReceiptItem", back_populates="ingredient")
    fridge_items = relationship("FridgeItem", back_populates="ingredient")
    guide = relationship("IngredientGuide", back_populates="ingredient", uselist=False, cascade="all, delete-orphan")
    recipe_ingredients = relationship("RecipeIngredient", back_populates="ingredient")
    storage_standards = relationship("IngredientStorageStandard", back_populates="ingredient", cascade="all, delete-orphan")


class IngredientAlias(Base):
    """식재료의 다른 이름을 저장하는 ORM 모델입니다."""

    __tablename__ = "ingredient_aliases"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "alias_name", name="uq_ingredient_aliases_ingredient_alias"),
        Index("idx_ingredient_aliases_alias_name", "alias_name"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 별칭이 가리키는 식재료 마스터를 연결합니다.
    ingredient = relationship("Ingredient", back_populates="aliases")


class IngredientStorageStandard(Base):
    """식재료 보관 기준 (수명 캐시)을 표현하는 ORM 모델입니다."""

    __tablename__ = "ingredient_storage_standards"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "storage_location", name="uq_ingredient_storage_standards"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False)
    storage_location = Column(String(50), nullable=False)
    lifespan_days = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 식재료 마스터와의 관계
    ingredient = relationship("Ingredient", back_populates="storage_standards")


class Receipt(Base):
    """사용자가 업로드한 영수증 정보를 표현하는 ORM 모델입니다."""

    __tablename__ = "receipts"
    __table_args__ = (Index("idx_receipts_user_id", "user_id"),)

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_file_name = Column(String(255), nullable=True)
    original_file_path = Column(String(500), nullable=True)
    store_name = Column(Text, nullable=True)
    purchased_at = Column(DateTime(timezone=True), nullable=True)
    total_price = Column(Integer, nullable=True)
    confirmed_result_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 영수증 소유자와 OCR로 추출된 품목을 연결합니다.
    user = relationship("User", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")


class ReceiptItem(Base):
    """영수증에서 추출된 개별 구매 품목을 표현하는 ORM 모델입니다."""

    __tablename__ = "receipt_items"
    __table_args__ = (
        Index("idx_receipt_items_receipt_id", "receipt_id"),
        Index("idx_receipt_items_ingredient_id", "ingredient_id"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    receipt_id = Column(BigIntPrimaryKey, ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="SET NULL"), nullable=True)
    raw_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(30), nullable=True)
    item_amount = Column(Integer, nullable=True)
    storage_method = Column(String(50), nullable=True)
    item_memo = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 원본 영수증, 매칭된 식재료, 냉장고 등록 항목을 연결합니다.
    receipt = relationship("Receipt", back_populates="items")
    ingredient = relationship("Ingredient", back_populates="receipt_items")
    fridge_items = relationship("FridgeItem", back_populates="receipt_item")


# 사용자가 현재 냉장고에 보유한 재료와 소비기한 정보를 저장한다.
class FridgeItem(Base):
    """사용자가 보유한 냉장고 식재료를 표현하는 ORM 모델입니다."""

    __tablename__ = "fridge_items"
    __table_args__ = (
        CheckConstraint("status IN ('normal', 'expiring', 'expired', 'used')", name="ck_fridge_items_status"),
        Index("idx_fridge_items_user_id", "user_id"),
        Index("idx_fridge_items_ingredient_id", "ingredient_id"),
        Index("idx_fridge_items_receipt_item_id", "receipt_item_id"),
        Index("idx_fridge_items_expiry_date", "expiry_date"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    receipt_item_id = Column(
        BigIntPrimaryKey,
        ForeignKey("receipt_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    display_name = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(30), nullable=True)
    storage_location = Column(String(50), nullable=True)
    purchased_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, server_default="normal")
    is_ai_recommended = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 냉장고 항목의 소유자, 식재료, 영수증 등록 항목, 알림을 연결합니다.
    user = relationship("User", back_populates="fridge_items")
    ingredient = relationship("Ingredient", back_populates="fridge_items")
    receipt_item = relationship("ReceiptItem", back_populates="fridge_items")
    notifications = relationship("Notification", back_populates="fridge_item", cascade="all, delete-orphan")


class IngredientGuide(Base):
    """식재료별 보관/손질 가이드를 표현하는 ORM 모델입니다."""

    __tablename__ = "ingredient_guides"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, unique=True)
    storage_location = Column(String(50), nullable=True)
    storage_method = Column(Text, nullable=True)
    prep_method = Column(Text, nullable=True)
    wash_method = Column(Text, nullable=True)
    freshness_check = Column(Text, nullable=True)
    caution = Column(Text, nullable=True)
    source_url = Column(String(500), nullable=True)
    validation_status = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 가이드가 설명하는 식재료 마스터를 연결합니다.
    ingredient = relationship("Ingredient", back_populates="guide")


class FoodGuideSuggestion(Base):
    """사용자가 제보한 식재료 가이드 후보를 검토 전까지 보관합니다."""

    __tablename__ = "food_guide_suggestions"
    __table_args__ = (
        CheckConstraint(
            "guide_type IN ('storage', 'prep', 'washing', 'freshness')",
            name="ck_food_guide_suggestions_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_food_guide_suggestions_status",
        ),
        Index(
            "idx_food_guide_suggestions_review",
            "status",
            "ingredient_code",
            "guide_type",
        ),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(
        BigIntPrimaryKey,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ingredient_code = Column(String(100), nullable=False)
    ingredient_name = Column(String(255), nullable=False)
    guide_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    source_name = Column(String(255), nullable=True)
    source_url = Column(String(1000), nullable=True)
    status = Column(String(30), nullable=False, server_default="pending")
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)


class Recipe(Base):
    """추천과 상세 조회에 사용하는 레시피 정보를 표현하는 ORM 모델입니다."""

    __tablename__ = "recipes"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    serving_size = Column(Integer, nullable=True)
    cooking_time = Column(Integer, nullable=True)
    difficulty = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True)
    recipe_steps = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recipe_ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    recommendation_results = relationship("RecommendationResult", back_populates="recipe", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    """레시피에 필요한 식재료와 수량을 표현하는 ORM 모델입니다."""

    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        Index("idx_recipe_ingredients_recipe_id", "recipe_id"),
        Index("idx_recipe_ingredients_ingredient_id", "ingredient_id"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    recipe_id = Column(BigIntPrimaryKey, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(BigIntPrimaryKey, ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    raw_ingredient_name = Column(String(255), nullable=True)
    required_quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(30), nullable=True)
    is_main_ingredient = Column(Boolean, nullable=False, server_default=false())

    # 레시피와 식재료 마스터를 연결합니다.
    recipe = relationship("Recipe", back_populates="recipe_ingredients")
    ingredient = relationship("Ingredient", back_populates="recipe_ingredients")


# 사용자가 저장하거나 추천받은 레시피 결과를 저장한다.
class RecommendationResult(Base):
    """사용자별 레시피 추천 결과를 표현하는 ORM 모델입니다."""

    __tablename__ = "recommendation_results"
    __table_args__ = (Index("idx_recommendation_results_user_id", "user_id"),)

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipe_id = Column(BigIntPrimaryKey, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    recommendation_type = Column(String(50), nullable=True)
    match_score = Column(Numeric(5, 2), nullable=True)
    owned_ingredient_count = Column(Integer, nullable=True)
    missing_ingredient_count = Column(Integer, nullable=True)
    missing_ingredients = Column(Text, nullable=True)
    rank_no = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 추천 결과의 대상 사용자와 레시피를 연결합니다.
    user = relationship("User", back_populates="recommendation_results")
    recipe = relationship("Recipe", back_populates="recommendation_results")


class Notification(Base):
    """소비기한 관련 사용자 알림을 표현하는 ORM 모델입니다."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("notification_type IN ('expiring_soon', 'expired')", name="ck_notifications_type"),
        CheckConstraint("status IN ('pending', 'sent', 'read', 'failed')", name="ck_notifications_status"),
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_fridge_item_id", "fridge_item_id"),
        Index("idx_notifications_status", "status"),
    )

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
    user_id = Column(BigIntPrimaryKey, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fridge_item_id = Column(BigIntPrimaryKey, ForeignKey("fridge_items.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(String(50), nullable=False)
    target_date = Column(Date, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, server_default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # 알림 수신 사용자와 대상 냉장고 항목을 연결합니다.
    user = relationship("User", back_populates="notifications")
    fridge_item = relationship("FridgeItem", back_populates="notifications")
