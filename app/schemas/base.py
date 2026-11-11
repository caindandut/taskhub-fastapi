from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common model configuration."""

    model_config = ConfigDict(str_strip_whitespace=True)
