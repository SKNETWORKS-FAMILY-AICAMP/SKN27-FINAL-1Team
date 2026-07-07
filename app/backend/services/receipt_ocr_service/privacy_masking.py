import re
from typing import Optional


MASK_CARD_NUMBER = "[\uce74\ub4dc\ubc88\ud638 \ub9c8\uc2a4\ud0b9]"
MASK_APPROVAL_NUMBER = "[\uc2b9\uc778\ubc88\ud638 \ub9c8\uc2a4\ud0b9]"
MASK_PHONE_NUMBER = "[\uc804\ud654\ubc88\ud638 \ub9c8\uc2a4\ud0b9]"
MASK_ADDRESS = "[\uc8fc\uc18c \ub9c8\uc2a4\ud0b9]"

CARD_NUMBER_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
PHONE_NUMBER_PATTERN = re.compile(
    r"(?<!\d)(?:01[016789]|02|0[3-6][1-5])[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
    r"|(?<!\d)1[568]\d{2}[-.\s]?\d{4}(?!\d)"
)
APPROVAL_NUMBER_PATTERN = re.compile(
    r"((?:\uc2b9\uc778|approval)\s*(?:\ubc88\ud638|no\.?|number)?\s*[:#-]?\s*)"
    r"([A-Za-z0-9-]{4,})",
    re.IGNORECASE,
)
LABELED_ADDRESS_PATTERN = re.compile(
    r"((?:\uc8fc\uc18c|\ub9e4\uc7a5\uc8fc\uc18c|\uac00\ub9f9\uc810\uc8fc\uc18c|\uc0ac\uc5c5\uc7a5\uc18c\uc7ac\uc9c0)\s*[:#-]?\s*)"
    r"([^\n\r,|]+)"
)
KOREAN_ADDRESS_PATTERN = re.compile(
    r"(?:[\uac00-\ud7a3]+(?:\uc2dc|\ub3c4)\s+)?"
    r"[\uac00-\ud7a3]+(?:\uc2dc|\uad70|\uad6c)\s+"
    r"[\uac00-\ud7a30-9]+(?:\uc74d|\uba74|\ub3d9|\ub85c|\uae38)"
    r"(?:\s*[\uac00-\ud7a30-9.-]+){0,4}"
)


def mask_sensitive_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    masked = APPROVAL_NUMBER_PATTERN.sub(lambda match: f"{match.group(1)}{MASK_APPROVAL_NUMBER}", value)
    masked = CARD_NUMBER_PATTERN.sub(MASK_CARD_NUMBER, masked)
    masked = PHONE_NUMBER_PATTERN.sub(MASK_PHONE_NUMBER, masked)
    masked = LABELED_ADDRESS_PATTERN.sub(lambda match: f"{match.group(1)}{MASK_ADDRESS}", masked)
    masked = KOREAN_ADDRESS_PATTERN.sub(MASK_ADDRESS, masked)
    return masked
