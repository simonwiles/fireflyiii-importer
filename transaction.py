from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class Transaction:
    date: datetime
    description: str
    amount: float
    account: str
    external_id: str
    type: Optional[str] = None
    source_name: Optional[str] = None
    destination_name: Optional[str] = None


@dataclass
class Config:
    account: str
    description_column: str
    date_column: str
    date_format: str
    date_window_days: Optional[int] = None
    amount_column: str | None = None
    invert_amount: bool = False
    credit_column: str | None = None
    debit_column: str | None = None
    additional_uid_column: str | None = None
    transfers_out: Dict[str, str] = field(default_factory=dict)
    transfers_in: Dict[str, str] = field(default_factory=dict)
