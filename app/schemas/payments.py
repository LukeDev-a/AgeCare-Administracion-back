from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class PaymentOperation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    action: Literal['cancel', 'extend', 'refund']
    version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=5, max_length=500)
    confirmed: StrictBool
    days: int | None = Field(None, ge=1, le=90, strict=True)
