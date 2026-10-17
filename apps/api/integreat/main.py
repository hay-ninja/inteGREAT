"""FastAPI app factory. Run from apps/api: `uvicorn integreat.main:create_app --factory --reload`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .api.ws import Hub
from .config import Settings, load_settings
from .service import Service, ServiceError
from .storage.db import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="inteGREAT API", version="0.1.0")
    store = Store(settings.db_path)
    app.state.service = Service(store, settings, Hub(store))

    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, e: ServiceError):
        return JSONResponse(status_code=e.status, content={"error": {"code": e.code, "message": e.message}})

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    app.include_router(router)
    return app

