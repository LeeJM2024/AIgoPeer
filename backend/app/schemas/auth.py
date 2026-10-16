from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class LoginInput(BaseModel):
    account: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_no: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=32,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
        ),
    ]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    password: str = Field(min_length=10, max_length=128)

    @field_validator("password")
    @classmethod
    def nonblank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("password must not be blank")
        return value
