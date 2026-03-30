import logging

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class FetchError(Exception):
    pass


class InvalidContentTypeError(FetchError):
    pass


class UpstreamTimeoutError(FetchError):
    pass


async def fetch_html(url: str) -> str:
    settings = get_settings()
    logger.info("fetch start", extra={"url": url})
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "auth-detector/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        logger.error("fetch timeout", extra={"url": url})
        raise UpstreamTimeoutError("Request timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.error("fetch failure", extra={"url": url, "status_code": exc.response.status_code})
        raise FetchError(f"Upstream returned status {exc.response.status_code}.") from exc
    except httpx.HTTPError as exc:
        logger.error("fetch failure", extra={"url": url})
        raise FetchError("Failed to fetch URL.") from exc

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        logger.error("invalid content type", extra={"url": url, "content_type": content_type})
        raise InvalidContentTypeError("URL did not return HTML content.")

    logger.info("fetch end", extra={"url": url, "status_code": response.status_code})
    return response.text
