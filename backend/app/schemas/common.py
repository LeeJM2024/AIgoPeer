from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    data: Any
