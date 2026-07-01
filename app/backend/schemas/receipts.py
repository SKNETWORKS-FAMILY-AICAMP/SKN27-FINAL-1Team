from typing import List, Optional

from pydantic import BaseModel, Field


class ReceiptOcrItem(BaseModel):
    raw_name: str = Field(..., description="Item name read from the receipt")
    normalized_name: Optional[str] = Field(default=None, description="User-confirmed standard item name")
    quantity: float = Field(default=1, description="Item quantity; decimal values are allowed")
    unit: str = Field(default="개", description="Display unit. Use either '개' or 'kg'")
    item_amount: Optional[int] = Field(default=None, description="Line item amount")


class ReceiptUploadResponse(BaseModel):
    receipt_id: Optional[int] = Field(default=None, description="Created receipt ID")
    original_file_name: Optional[str] = Field(default=None, description="Uploaded file name")
    original_file_path: Optional[str] = Field(default=None, description="Saved original image path")
    store_name: Optional[str] = Field(default=None, description="Store name read from the receipt")
    purchase_datetime: Optional[str] = Field(default=None, description="Purchase datetime: YYYY-MM-DD HH:mm:ss")
    items: List[ReceiptOcrItem] = Field(default_factory=list, description="OCR item candidates")
    total_item_count: Optional[float] = Field(default=None, description="Total item quantity")
    total_amount: Optional[int] = Field(default=None, description="Receipt total amount; reference value")
    currency: str = Field(default="KRW", description="Currency code")
    confidence_note: Optional[str] = Field(default=None, description="Uncertain OCR details")


class ReceiptConfirmItem(BaseModel):
    raw_name: str = Field(..., description="Original receipt item name")
    normalized_name: Optional[str] = Field(default=None, description="Final item name")
    quantity: float = Field(default=1, description="Final quantity; decimal values are allowed")
    unit: str = Field(default="개", description="Final unit. Use either '개' or 'kg'")
    item_amount: Optional[int] = Field(default=None, description="Final line item amount")
    storage_method: str = Field(default="냉장", description="Storage method")
    item_memo: Optional[str] = Field(default=None, description="User memo")


class ReceiptConfirmRequest(BaseModel):
    receipt_id: int = Field(..., description="Receipt ID returned by upload API")
    store_name: Optional[str] = Field(default=None, description="Final store name")
    purchase_datetime: Optional[str] = Field(default=None, description="Final purchase datetime")
    total_amount: Optional[int] = Field(default=None, description="Receipt total amount; reference value")
    items: List[ReceiptConfirmItem] = Field(default_factory=list, description="User-confirmed item list")
    calendar_cost_enabled: bool = Field(default=True, description="Whether to create a calendar cost event")


class ReceiptUpdateRequest(BaseModel):
    store_name: str = Field(..., min_length=1, max_length=100, description="New store name (receipt title)")


class ReceiptHistoryItem(BaseModel):
    raw_name: str = Field(..., description="Original receipt item name")
    normalized_name: Optional[str] = Field(default=None, description="Confirmed item name")
    quantity: Optional[float] = Field(default=None, description="Item quantity")
    unit: Optional[str] = Field(default=None, description="Item unit")
    item_amount: Optional[int] = Field(default=None, description="Line item amount")
    storage_method: Optional[str] = Field(default=None, description="Storage method")


class ReceiptHistoryEntry(BaseModel):
    receipt_id: int = Field(..., description="Receipt ID")
    store_name: Optional[str] = Field(default=None, description="Store name")
    purchase_datetime: Optional[str] = Field(default=None, description="Purchase datetime: YYYY-MM-DD HH:mm")
    total_amount: Optional[int] = Field(default=None, description="Receipt total amount")
    item_count: int = Field(default=0, description="Number of registered items")
    original_file_name: Optional[str] = Field(default=None, description="Uploaded file name")
    original_file_path: Optional[str] = Field(default=None, description="Saved original image path")
    items: List[ReceiptHistoryItem] = Field(default_factory=list, description="Registered items")


class ReceiptHistoryResponse(BaseModel):
    receipts: List[ReceiptHistoryEntry] = Field(default_factory=list, description="Recent registered receipts")
