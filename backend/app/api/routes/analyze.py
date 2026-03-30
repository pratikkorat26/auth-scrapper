import logging

from fastapi import APIRouter, HTTPException, status

from ...models.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse
from ...services.analysis import analyze_url
from ...services.fetcher import FetchError, InvalidContentTypeError, UpstreamTimeoutError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    logger.info("request received", extra={"url": payload.url})
    logger.info("url normalized", extra={"url": payload.url})

    try:
        result = await analyze_url(payload.url)
    except InvalidContentTypeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except UpstreamTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("unexpected error", extra={"url": payload.url})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error.") from exc

    logger.info(
        "detection result",
        extra={
            "url": payload.url,
            "found": result.detection.found,
            "confidence": result.detection.confidence,
            "analysis_mode": result.analysis_mode,
        },
    )
    return AnalyzeResponse(
        url=payload.url,
        found=result.detection.found,
        confidence=result.detection.confidence,
        status=result.detection.status,
        signals=result.detection.signals,
        snippet=result.detection.snippet,
        message=result.detection.message,
        analysis_mode=result.analysis_mode,
        fallback_used=result.fallback_used,
        interaction_used=result.interaction_used,
        surface_type=result.detection.surface_type,
        fields=[field.__dict__ for field in result.detection.fields],
        actions=[action.__dict__ for action in result.detection.actions],
        providers=result.detection.providers,
        alternate_candidates=[candidate.__dict__ for candidate in result.detection.alternate_candidates],
    )
