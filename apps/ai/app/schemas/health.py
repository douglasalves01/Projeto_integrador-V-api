from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str
    model_version: str
    models_loaded: bool

    model_config = ConfigDict(from_attributes=True)


class DependencyStatus(BaseModel):
    status: str
    detail: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DetailedHealthResponse(BaseModel):
    status: str
    service: str
    model_version: str
    models_loaded: bool
    mysql: DependencyStatus
    redis: DependencyStatus

    model_config = ConfigDict(from_attributes=True)
