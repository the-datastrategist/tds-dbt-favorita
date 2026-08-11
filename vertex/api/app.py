"""FastAPI application exposing complete, immutable forecast publication versions."""

from __future__ import annotations

import os
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vertex.api.repository import (
    BigQueryForecastRepository,
    ForecastFilters,
    ForecastPageResult,
    ForecastRepository,
    PublicationScope,
    canonical_entity_key,
)


class ErrorBody(BaseModel):
    code: str
    message: str


class ForecastPage(BaseModel):
    forecast_run_id: str
    forecast_contract_name: str
    forecast_contract_hash: str
    publication_version: int
    destination: str
    delivery_status: str
    publication_row_count: int
    items: list[dict[str, Any]]
    next_page_token: str | None = None


class QueryFilters(BaseModel):
    entity_key: str | None = None
    target_start: date | None = None
    target_end: date | None = None
    horizon: list[int] = Field(default_factory=list)
    limit: int = 100
    page_token: str | None = None


def _repository() -> ForecastRepository:
    project_id = os.getenv("GOOGLE_PROJECT_ID", "tds-favorita")
    dataset = os.getenv("DBT_DATASET", "favorita")
    return BigQueryForecastRepository(
        project_id=project_id,
        table_prefix=f"{project_id}.{dataset}",
    )


def _filters(
    entity_key: str | None = None,
    target_start: date | None = None,
    target_end: date | None = None,
    horizon: Annotated[list[int] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    page_token: str | None = None,
) -> QueryFilters:
    if target_start and target_end and target_start > target_end:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_date_range", "message": "target_start exceeds target_end"},
        )
    if horizon and any(value < 1 for value in horizon):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_horizon", "message": "horizons must be positive"},
        )
    try:
        normalized_entity = canonical_entity_key(entity_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_entity_key", "message": str(exc)},
        ) from exc
    return QueryFilters(
        entity_key=normalized_entity,
        target_start=target_start,
        target_end=target_end,
        horizon=horizon or [],
        limit=limit,
        page_token=page_token,
    )


def _response(result: ForecastPageResult) -> ForecastPage:
    return ForecastPage(
        forecast_run_id=result.scope.forecast_run_id,
        forecast_contract_name=result.scope.forecast_contract_name,
        forecast_contract_hash=result.scope.forecast_contract_hash,
        publication_version=result.scope.publication_version,
        destination=result.scope.destination,
        delivery_status=result.scope.delivery_status,
        publication_row_count=result.scope.publication_row_count,
        items=result.rows,
        next_page_token=result.next_page_token,
    )


def _fetch(
    repository: ForecastRepository,
    scope: PublicationScope | None,
    filters: QueryFilters,
) -> ForecastPage:
    if scope is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "publication_not_found", "message": "publication version not found"},
        )
    try:
        result = repository.fetch_page(
            scope,
            filters=ForecastFilters(
                entity_key_json=filters.entity_key,
                target_start=filters.target_start,
                target_end=filters.target_end,
                horizons=tuple(filters.horizon),
            ),
            limit=filters.limit,
            page_token=filters.page_token,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_page_token", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "incomplete_publication", "message": str(exc)},
        ) from exc
    return _response(result)


def create_app(repository: ForecastRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="Forecast Retrieval API",
        version="1.0.0",
        description="Read-only access to complete, immutable forecast publication versions.",
    )
    if repository is not None:
        app.dependency_overrides[_repository] = lambda: repository

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            body = exc.detail
        else:
            body = {"code": "http_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "request validation failed",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def internal_error(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "forecast retrieval failed"},
        )

    @app.get("/healthz", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/forecasts/current", response_model=ForecastPage, tags=["forecasts"])
    def current_forecasts(
        contract_name: str,
        destination: str = "canonical_bigquery",
        filters: QueryFilters = Depends(_filters),
        repository: ForecastRepository = Depends(_repository),
    ) -> ForecastPage:
        scope = repository.resolve_current(
            contract_name=contract_name,
            destination=destination,
        )
        return _fetch(repository, scope, filters)

    @app.get(
        "/v1/forecasts/runs/{forecast_run_id}",
        response_model=ForecastPage,
        tags=["forecasts"],
    )
    def versioned_forecasts(
        forecast_run_id: str,
        publication_version: Annotated[int, Query(ge=1)],
        destination: str = "canonical_bigquery",
        filters: QueryFilters = Depends(_filters),
        repository: ForecastRepository = Depends(_repository),
    ) -> ForecastPage:
        scope = repository.resolve_version(
            forecast_run_id=forecast_run_id,
            publication_version=publication_version,
            destination=destination,
        )
        return _fetch(repository, scope, filters)

    return app


app = create_app()
