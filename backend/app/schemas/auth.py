from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    account: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
