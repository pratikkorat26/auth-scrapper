from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.analyze import router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Auth Detector", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0]
    return JSONResponse(status_code=400, content={"detail": first_error["msg"]})

