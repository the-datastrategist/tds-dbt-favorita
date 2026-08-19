"""FastAPI application exposing complete, immutable forecast publication versions."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from vertex.api.repository import (
    BigQueryForecastRepository,
    ExperimentOptions,
    ExperimentResult,
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

LOGGER = logging.getLogger("forecast_api.requests")


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
    nextPageToken: str | None = None


class ExperimentMetric(BaseModel):
    wape: float = Field(ge=0)
    bias: float
    coverage: float = Field(ge=0, le=1)


class ExperimentHorizon(ExperimentMetric):
    horizon: int = Field(ge=1)


class ExperimentSegment(ExperimentMetric):
    segmentId: str
    segmentName: str


class ExperimentOrigin(ExperimentMetric):
    origin: date


class ExperimentStatisticalEvidence(BaseModel):
    referenceRunId: str
    deltaWapePp: float
    confidenceLevel: float = Field(ge=0, le=1)
    ciLower: float
    ciUpper: float
    pValue: float = Field(ge=0, le=1)
    conclusion: Literal["meaningful", "inconclusive", "worse"]


class ExperimentForecastLink(BaseModel):
    runId: str
    entityId: str
    modelId: str
    exceptionState: Literal["all", "clear", "watch", "blocked"]


class ExperimentRunResponse(BaseModel):
    id: str
    label: str
    modelId: str
    modelName: str
    modelFamily: str
    featureVersion: str
    status: Literal["completed", "failed"]
    createdAt: datetime
    completedAt: datetime | None
    runtimeMinutes: float = Field(ge=0)
    comparable: bool
    summary: ExperimentMetric | None
    configuration: dict[str, str | float | bool]
    horizons: list[ExperimentHorizon]
    segments: list[ExperimentSegment]
    rollingOrigins: list[ExperimentOrigin]
    statisticalEvidence: ExperimentStatisticalEvidence | None
    forecastLink: ExperimentForecastLink | None


class ExperimentOptionsResponse(BaseModel):
    runs: list[dict[str, str | bool]]
    models: list[dict[str, str]]
    modelFamilies: list[str]
    featureVersions: list[str]
    statuses: list[Literal["completed", "failed"]]
    horizons: list[int]


class ExperimentListResponse(BaseModel):
    datasetKind: Literal["live"] = "live"
    runs: list[ExperimentRunResponse]


class ExperimentComparisonResponse(ExperimentListResponse):
    missingRunIds: list[str]


class OperationOutput(BaseModel):
    id: str
    entityLabel: str
    targetDate: date
    currentValue: float = Field(ge=0)
    exceptionState: Literal["clear", "watch", "blocked"]


class OperationRun(BaseModel):
    runId: str
    origin: date
    status: Literal["draft", "approved", "published", "superseded", "failed"]
    modelName: str
    outputCount: int = Field(ge=0)
    exceptionCount: int = Field(ge=0)
    overrideCount: int = Field(ge=0)
    approvalCount: int = Field(ge=0)
    publicationVersion: int | None = Field(default=None, ge=1)
    deliveryStatus: str
    fvaStatus: str
    plannerWapeFvaPoints: float | None
    totalWapeFvaPoints: float | None
    updatedAt: datetime
    outputs: list[OperationOutput]


class OperationsResponse(BaseModel):
    datasetKind: Literal["live"] = "live"
    runs: list[OperationRun]


class CapabilitiesResponse(BaseModel):
    mutationsEnabled: bool
    actor: str | None
    roles: list[Literal["viewer", "planner", "approver", "publisher", "operator"]]


class QueryFilters(BaseModel):
    entity_key: str | None = None
    target_start: date | None = None
    target_end: date | None = None
    horizon: list[int] = Field(default_factory=list)
    limit: int = 100
    page_token: str | None = None


class MutationBase(BaseModel):
    actor: str | None = Field(default=None, min_length=1, max_length=320)
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


class RevisionRequest(MutationBase):
    destination: str = Field(default="canonical_bigquery", min_length=1, max_length=256)
    publication_version: int = Field(ge=1)
    prior_version: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=128)
    comment: str = Field(min_length=1, max_length=2000)


class MutationResult(BaseModel):
    action: str
    retry: bool
    override_id: str | None = None
    approval_count: int | None = None
    override_count: int | None = None
    publication_count: int | None = None
    publication_version: int | None = None
    publication_event_id: str | None = None
    prior_version: int | None = None
    revision_count: int | None = None
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
    authorization_enabled: bool | None = None,
    role_members: dict[str, list[str]] | None = None,
) -> FastAPI:
    mutations_enabled = (
        os.getenv("FORECAST_API_MUTATIONS_ENABLED", "false").lower() == "true"
        if mutations_enabled is None
        else mutations_enabled
    )
    authorization_enabled = (
        os.getenv("FORECAST_API_AUTHORIZATION_ENABLED", "false").lower() == "true"
        if authorization_enabled is None
        else authorization_enabled
    )
    if role_members is None:
        try:
            configured_roles = json.loads(os.getenv("FORECAST_API_ROLE_MEMBERS_JSON", "{}"))
            role_members = {
                str(role): [str(member).lower() for member in members]
                for role, members in configured_roles.items()
                if isinstance(members, list)
            }
        except json.JSONDecodeError as exc:
            raise ValueError("FORECAST_API_ROLE_MEMBERS_JSON must be valid JSON") from exc
    app = FastAPI(
        title="Forecast Operations API",
        version="1.3.0",
        description=(
            "Read complete immutable forecast versions and append governed lifecycle mutations."
        ),
    )
    if repository is not None:
        app.dependency_overrides[_repository] = lambda: repository

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: Any) -> Any:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        LOGGER.info(
            json.dumps(
                {
                    "event": "forecast_api_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
                sort_keys=True,
            )
        )
        return response

    def identity(request: Request) -> str | None:
        raw = request.headers.get("X-Goog-Authenticated-User-Email")
        if not raw:
            return None
        return raw.rsplit(":", 1)[-1].strip().lower() or None

    def roles_for(
        actor: str | None,
    ) -> list[Literal["viewer", "planner", "approver", "publisher", "operator"]]:
        if actor is None:
            return ["viewer"]
        direct = {role for role, members in (role_members or {}).items() if actor in members}
        inherited = {"viewer"}
        if "operator" in direct:
            inherited.add("operator")
        if "planner" in direct:
            inherited.add("planner")
        if "approver" in direct:
            inherited.update({"planner", "approver"})
        if "publisher" in direct:
            inherited.update({"planner", "approver", "publisher"})
        return [
            role
            for role in ("approver", "operator", "planner", "publisher", "viewer")
            if role in inherited
        ]

    def authorize(request: Request, role: str, fallback_actor: str | None) -> str:
        if not mutations_enabled:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "mutations_disabled",
                    "message": "lifecycle mutations are disabled for this deployment",
                },
            )
        authenticated = identity(request)
        if authorization_enabled:
            if authenticated is None:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "authentication_required",
                        "message": "IAP identity is required",
                    },
                )
            if role not in roles_for(authenticated):
                raise HTTPException(
                    status_code=403,
                    detail={"code": "role_required", "message": f"{role} role is required"},
                )
            return authenticated
        if fallback_actor:
            return fallback_actor
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actor_required",
                "message": "actor is required without IAP authorization",
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

    @app.get(
        "/v1/capabilities",
        response_model=CapabilitiesResponse,
        tags=["forecastlab"],
    )
    def capabilities(request: Request) -> CapabilitiesResponse:
        actor = identity(request)
        return CapabilitiesResponse(
            mutationsEnabled=bool(mutations_enabled and (actor or not authorization_enabled)),
            actor=actor,
            roles=roles_for(actor),
        )

    @app.get(
        "/v1/operations",
        response_model=OperationsResponse,
        tags=["forecastlab"],
    )
    def operations(
        repository: ForecastRepository = Depends(_repository),
    ) -> OperationsResponse:
        return OperationsResponse(
            runs=[OperationRun.model_validate(run) for run in repository.operations_snapshot()]
        )

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
        run_id: Annotated[str | None, Query(min_length=1)] = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerOptionsResponse:
        result: ForecastExplorerOptions = repository.forecast_explorer_options(
            forecast_run_id=run_id
        )
        if run_id is not None and not result.entities:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "forecast_run_not_found",
                    "message": "forecast run has no delivered canonical publication",
                },
            )
        return ExplorerOptionsResponse(
            runs=[ExplorerRun.model_validate(value) for value in result.runs],
            entities=[ExplorerEntity.model_validate(value) for value in result.entities],
            models=[ExplorerModel.model_validate(value) for value in result.models],
            horizons=result.horizons,
        )

    @app.get(
        "/v1/experiments/options",
        response_model=ExperimentOptionsResponse,
        tags=["forecastlab"],
    )
    def experiment_options(
        repository: ForecastRepository = Depends(_repository),
    ) -> ExperimentOptionsResponse:
        result: ExperimentOptions = repository.experiment_options()
        return ExperimentOptionsResponse(
            runs=result.runs,
            models=result.models,
            modelFamilies=result.model_families,
            featureVersions=result.feature_versions,
            statuses=[status for status in ("completed", "failed") if status in result.statuses],
            horizons=result.horizons,
        )

    @app.get(
        "/v1/experiments",
        response_model=ExperimentListResponse,
        tags=["forecastlab"],
    )
    def experiments(
        model_id: str | None = None,
        model_family: str | None = None,
        feature_version: str | None = None,
        status: Annotated[Literal["completed", "failed"] | None, Query()] = None,
        horizon: Annotated[int | None, Query(ge=1)] = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExperimentListResponse:
        result: ExperimentResult = repository.experiment_runs(
            model_id=model_id,
            model_family=model_family,
            feature_version=feature_version,
            status=status,
            horizon=horizon,
        )
        return ExperimentListResponse(
            runs=[ExperimentRunResponse.model_validate(run) for run in result.runs]
        )

    @app.get(
        "/v1/experiments/compare",
        response_model=ExperimentComparisonResponse,
        tags=["forecastlab"],
    )
    def compare_experiments(
        runs: Annotated[list[str], Query(min_length=2, max_length=5)],
        repository: ForecastRepository = Depends(_repository),
    ) -> ExperimentComparisonResponse:
        unique_runs = tuple(dict.fromkeys(runs))
        if len(unique_runs) < 2:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_experiment_comparison",
                    "message": "comparison requires two to five unique run IDs",
                },
            )
        result: ExperimentResult = repository.experiment_runs(run_ids=unique_runs)
        return ExperimentComparisonResponse(
            runs=[ExperimentRunResponse.model_validate(run) for run in result.runs],
            missingRunIds=result.missing_run_ids,
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
            nextPageToken=result.next_page_token,
        )

    def read_explorer_forecasts(
        *,
        forecast_run_id: str,
        entity_id: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
        target_start: date | None,
        target_end: date | None,
        limit: int,
        page_token: str | None,
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
        if target_start and target_end and target_start > target_end:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_date_range",
                    "message": "target_start exceeds target_end",
                },
            )
        try:
            result = repository.forecast_explorer_result(
                forecast_run_id=forecast_run_id,
                entity_key_json=entity_key,
                model_id=model_id,
                horizon=horizon,
                exception_state=exception_state,
                target_start=target_start,
                target_end=target_end,
                limit=limit,
                page_token=page_token,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_page_token", "message": str(exc)},
            ) from exc
        return explorer_response(result)

    @app.get("/v1/forecasts", response_model=ExplorerResponse, tags=["forecastlab"])
    def forecast_explorer(
        run_id: Annotated[str, Query(min_length=1)],
        entity_id: Annotated[str, Query(min_length=1)],
        model_id: Annotated[str, Query(min_length=1)],
        horizon: Annotated[int | None, Query(ge=1)] = None,
        exception_state: Annotated[str | None, Query(pattern="^(clear|watch|blocked)$")] = None,
        target_start: date | None = None,
        target_end: date | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        page_token: str | None = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerResponse:
        return read_explorer_forecasts(
            forecast_run_id=run_id,
            entity_id=entity_id,
            model_id=model_id,
            horizon=horizon,
            exception_state=exception_state,
            target_start=target_start,
            target_end=target_end,
            limit=limit,
            page_token=page_token,
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
        target_start: date | None = None,
        target_end: date | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        page_token: str | None = None,
        repository: ForecastRepository = Depends(_repository),
    ) -> ExplorerResponse:
        return read_explorer_forecasts(
            forecast_run_id=forecast_run_id,
            entity_id=entity_id,
            model_id=model_id,
            horizon=horizon,
            exception_state=exception_state,
            target_start=target_start,
            target_end=target_end,
            limit=limit,
            page_token=page_token,
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
    )
    def create_override(
        http_request: Request,
        request: OverrideRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        actor = authorize(http_request, "planner", request.actor)
        return _mutation(
            lambda: repository.create_override(
                forecast_run_id=request.forecast_run_id,
                forecast_output_id=request.forecast_output_id,
                override_value=request.override_value,
                reason_code=request.reason_code,
                comment=request.comment,
                actor=actor,
                idempotency_key=request.idempotency_key,
            )
        )

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/approve",
        response_model=MutationResult,
        tags=["lifecycle"],
    )
    def approve_run(
        forecast_run_id: str,
        http_request: Request,
        request: ApprovalRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        actor = authorize(http_request, "approver", request.actor)
        return _mutation(
            lambda: repository.approve_run(
                forecast_run_id=forecast_run_id,
                reason_code=request.reason_code,
                comment=request.comment,
                actor=actor,
                idempotency_key=request.idempotency_key,
            )
        )

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/publish",
        response_model=MutationResult,
        tags=["lifecycle"],
    )
    def publish_run(
        forecast_run_id: str,
        http_request: Request,
        request: PublicationRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        actor = authorize(http_request, "publisher", request.actor)
        return _mutation(
            lambda: repository.publish_run(
                forecast_run_id=forecast_run_id,
                approval_idempotency_key=request.approval_idempotency_key,
                destination=request.destination,
                publication_version=request.publication_version,
                actor=actor,
                idempotency_key=request.idempotency_key,
            )
        )

    def revision_response(
        action: Literal["supersede", "rollback"],
        forecast_run_id: str,
        http_request: Request,
        request: RevisionRequest,
        repository: ForecastRepository,
    ) -> MutationResult:
        actor = authorize(http_request, "publisher", request.actor)
        operation = repository.supersede_run if action == "supersede" else repository.rollback_run
        return _mutation(
            lambda: operation(
                forecast_run_id=forecast_run_id,
                prior_version=request.prior_version,
                publication_version=request.publication_version,
                destination=request.destination,
                reason_code=request.reason_code,
                comment=request.comment,
                actor=actor,
                idempotency_key=request.idempotency_key,
            )
        )

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/supersede",
        response_model=MutationResult,
        tags=["lifecycle"],
    )
    def supersede_run(
        forecast_run_id: str,
        http_request: Request,
        request: RevisionRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        return revision_response("supersede", forecast_run_id, http_request, request, repository)

    @app.post(
        "/v1/forecast-runs/{forecast_run_id}/rollback",
        response_model=MutationResult,
        tags=["lifecycle"],
    )
    def rollback_run(
        forecast_run_id: str,
        http_request: Request,
        request: RevisionRequest,
        repository: ForecastRepository = Depends(_repository),
    ) -> MutationResult:
        return revision_response("rollback", forecast_run_id, http_request, request, repository)

    frontend_dist = Path(
        os.getenv("FORECASTLAB_DIST_DIR", Path(__file__).parents[2] / "frontend" / "dist")
    ).resolve()
    if (frontend_dist / "index.html").is_file():

        @app.get("/{asset_path:path}", include_in_schema=False)
        def forecastlab_spa(asset_path: str) -> FileResponse:
            requested = (frontend_dist / asset_path).resolve()
            if requested.is_relative_to(frontend_dist) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
