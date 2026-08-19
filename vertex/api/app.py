"""FastAPI application exposing complete, immutable forecast publication versions."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from vertex.api.repository import (
    BigQueryForecastRepository,
    ForecastExplorerOptions,
    ForecastExplorerResult,
    ForecastFilters,
    ForecastPageResult,
    ForecastRepository,
    MutationConflictError,
    MutationNotFoundError,
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


class ExplorerRun(BaseModel):
    id: str
    label: str
    origin: date
    publicationStatus: Literal["draft", "published", "superseded"] | None = None


class ExplorerEntity(BaseModel):
    id: str
    name: str
    hierarchyNode: str
    hierarchyLevel: str


class ExplorerModel(BaseModel):
    id: str
    name: str


class ExplorerRow(BaseModel):
    runId: str
    entityId: str
    modelId: str
    targetDate: date
    horizon: int = Field(ge=1)
    actual: float | None = Field(default=None, ge=0)
    p10: float = Field(ge=0)
    p50: float = Field(ge=0)
    p90: float = Field(ge=0)
    statisticalForecast: float = Field(ge=0)
    publishedForecast: float = Field(ge=0)
    strategy: str
    exceptionState: Literal["clear", "watch", "blocked"]

    @model_validator(mode="after")
    def quantiles_are_ordered(self) -> "ExplorerRow":
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError("forecast quantiles must be ordered")
        return self


class ExplorerProvenance(BaseModel):
    contractName: str
    contractHash: str
    modelRunId: str
    calibrationRunId: str
    reconciliationRunId: str
    hierarchyVersion: str
    featureVersion: str
    featureAvailabilityHash: str
    dataCutoff: datetime
    codeSha: str
    publicationVersion: str


def _exception_states() -> list[Literal["clear", "watch", "blocked"]]:
    return ["clear", "watch", "blocked"]


class ExplorerOptionsResponse(BaseModel):
    runs: list[ExplorerRun]
    entities: list[ExplorerEntity]
    models: list[ExplorerModel]
    horizons: list[int]
    exceptionStates: list[Literal["clear", "watch", "blocked"]] = Field(
        default_factory=_exception_states
    )


class ExplorerResponse(BaseModel):
    datasetKind: Literal["live"] = "live"
    run: ExplorerRun
    entity: ExplorerEntity
    model: ExplorerModel
    rows: list[ExplorerRow]
    provenance: ExplorerProvenance


class QueryFilters(BaseModel):
    entity_key: str | None = None
    target_start: date | None = None
    target_end: date | None = None
    horizon: list[int] = Field(default_factory=list)
    limit: int = 100
    page_token: str | None = None


class MutationBase(BaseModel):
    actor: str = Field(min_length=1, max_length=320)
    idempotency_key: str = Field(min_length=1, max_length=256)


class OverrideRequest(MutationBase):
    forecast_run_id: str = Field(min_length=1, max_length=256)
    forecast_output_id: str = Field(min_length=1, max_length=256)
    override_value: float = Field(ge=0)
    reason_code: str = Field(min_length=1, max_length=128)
    comment: str = Field(min_length=1, max_length=2000)


class ApprovalRequest(MutationBase):
    reason_code: str = Field(min_length=1, max_length=128)
    comment: str = Field(min_length=1, max_length=2000)


class PublicationRequest(MutationBase):
    approval_idempotency_key: str = Field(min_length=1, max_length=256)
    destination: str = Field(default="canonical_bigquery", min_length=1, max_length=256)
    publication_version: int = Field(ge=1)


class MutationResult(BaseModel):
    action: str
    retry: bool
    override_id: str | None = None
    approval_count: int | None = None
    override_count: int | None = None
    publication_count: int | None = None
    publication_version: int | None = None
    publication_event_id: str | None = None
    webhook_delivery_status: str | None = None
    webhook_delivery_event_id: str | None = None


def _repository() -> ForecastRepository:
    project_id = os.getenv("GOOGLE_PROJECT_ID", "tds-favorita")
    dataset = os.getenv("DBT_DATASET", "favorita")
    return BigQueryForecastRepository(
        project_id=project_id,
        table_prefix=f"{project_id}.{dataset}",
        webhook_url=os.getenv("FORECAST_PUBLICATION_WEBHOOK_URL"),
        webhook_signing_secret=os.getenv("FORECAST_PUBLICATION_WEBHOOK_SIGNING_SECRET"),
        webhook_name=os.getenv("FORECAST_PUBLICATION_WEBHOOK_NAME", "default"),
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


def _mutation(call: Any) -> MutationResult:
    try:
        return MutationResult(**call())
    except MutationNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "mutation_target_not_found", "message": str(exc)},
        ) from exc
    except MutationConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "mutation_conflict", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_mutation", "message": str(exc)},
        ) from exc


def create_app(
    repository: ForecastRepository | None = None,
    *,
    mutations_enabled: bool | None = None,
) -> FastAPI:
    mutations_enabled = (
        os.getenv("FORECAST_API_MUTATIONS_ENABLED", "false").lower() == "true"
        if mutations_enabled is None
        else mutations_enabled
    )
    app = FastAPI(
        title="Forecast Operations API",
        version="1.2.0",
        description=(
            "Read complete immutable forecast versions and append governed lifecycle mutations."
        ),
    )
    if repository is not None:
        app.dependency_overrides[_repository] = lambda: repository

    def require_mutations() -> None:
        if not mutations_enabled:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "mutations_disabled",
                    "message": "lifecycle mutations are disabled for this deployment",
                },
            )

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
            content={"code": "internal_error", "message": "forecast API request failed"},
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
        "/v1/forecasts/options",
        response_model=ExplorerOptionsResponse,
        tags=["forecastlab"],
    )
    def forecast_explorer_options(
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerOptionsResponse:
        result: ForecastExplorerOptions = repository.forecast_explorer_options()
        return ExplorerOptionsResponse(
            runs=[ExplorerRun.model_validate(value) for value in result.runs],
            entities=[ExplorerEntity.model_validate(value) for value in result.entities],
            models=[ExplorerModel.model_validate(value) for value in result.models],
            horizons=result.horizons,
        )

    def explorer_response(result: ForecastExplorerResult | None) -> ExplorerResponse:
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "forecast_selection_not_found",
                    "message": "no delivered forecasts match the requested selection",
                },
            )
        return ExplorerResponse(
            run=ExplorerRun.model_validate(result.run),
            entity=ExplorerEntity.model_validate(result.entity),
            model=ExplorerModel.model_validate(result.model),
            rows=[ExplorerRow.model_validate(value) for value in result.rows],
            provenance=ExplorerProvenance.model_validate(result.provenance),
        )

    def read_explorer_forecasts(
        *,
        forecast_run_id: str,
        entity_id: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
        repository: ForecastRepository,
    ) -> ExplorerResponse:
        try:
            entity_key = canonical_entity_key(entity_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_entity_id", "message": str(exc)},
            ) from exc
        assert entity_key is not None
        return explorer_response(
            repository.forecast_explorer_result(
                forecast_run_id=forecast_run_id,
                entity_key_json=entity_key,
                model_id=model_id,
                horizon=horizon,
                exception_state=exception_state,
            )
        )

    @app.get("/v1/forecasts", response_model=ExplorerResponse, tags=["forecastlab"])
    def forecast_explorer(
        run_id: Annotated[str, Query(min_length=1)],
        entity_id: Annotated[str, Query(min_length=1)],
        model_id: Annotated[str, Query(min_length=1)],
        horizon: Annotated[int | None, Query(ge=1)] = None,
        exception_state: Annotated[str | None, Query(pattern="^(clear|watch|blocked)$")] = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerResponse:
        return read_explorer_forecasts(
            forecast_run_id=run_id,
            entity_id=entity_id,
            model_id=model_id,
            horizon=horizon,
            exception_state=exception_state,
            repository=repository,
        )

    @app.get(
        "/v1/forecast-runs/{forecast_run_id}",
        response_model=ExplorerResponse,
        tags=["forecastlab"],
    )
    def forecast_explorer_run(
        forecast_run_id: str,
        entity_id: Annotated[str, Query(min_length=1)],
        model_id: Annotated[str, Query(min_length=1)],
        horizon: Annotated[int | None, Query(ge=1)] = None,
        exception_state: Annotated[str | None, Query(pattern="^(clear|watch|blocked)$")] = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerResponse:
        return read_explorer_forecasts(
            forecast_run_id=forecast_run_id,
            entity_id=entity_id,
            model_id=model_id,
            horizon=horizon,
            exception_state=exception_state,
            repository=repository,
        )

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

    @app.post(
        "/v1/overrides",
        response_model=MutationResult,
        tags=["lifecycle"],
        dependencies=[Depends(require_mutations)],
    )
    def create_override(
        request: OverrideRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        return _mutation(
            lambda: repository.create_override(
                forecast_run_id=request.forecast_run_id,
                forecast_output_id=request.forecast_output_id,
                override_value=request.override_value,
                reason_code=request.reason_code,
                comment=request.comment,
                actor=request.actor,
                idempotency_key=request.idempotency_key,
            )
        )

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/approve",
        response_model=MutationResult,
        tags=["lifecycle"],
        dependencies=[Depends(require_mutations)],
    )
    def approve_run(
        forecast_run_id: str,
        request: ApprovalRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        return _mutation(
            lambda: repository.approve_run(
                forecast_run_id=forecast_run_id,
                reason_code=request.reason_code,
                comment=request.comment,
                actor=request.actor,
                idempotency_key=request.idempotency_key,
            )
        )

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/publish",
        response_model=MutationResult,
        tags=["lifecycle"],
        dependencies=[Depends(require_mutations)],
    )
    def publish_run(
        forecast_run_id: str,
        request: PublicationRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        return _mutation(
            lambda: repository.publish_run(
                forecast_run_id=forecast_run_id,
                approval_idempotency_key=request.approval_idempotency_key,
                destination=request.destination,
                publication_version=request.publication_version,
                actor=request.actor,
                idempotency_key=request.idempotency_key,
            )
        )

    return app


app = create_app()
