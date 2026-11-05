from pydantic import BaseModel


class FactSpec(BaseModel):
    value: str
    variants: list[str] = []
    match_tokens: list[str]
    asked_by: str | None = None
    label: str | None = None
