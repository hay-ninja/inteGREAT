"""FastAPI app factory. Run from apps/api: `uvicorn integreat.main:create_app --factory --reload`."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents.provider import LLMProvider
from .api.routes import router
from .api.visual import router as visual_router
from .api.ws import Hub
from .config import Settings, load_settings
from .observations.devices import DeviceManager
from .repair import DevinClientProtocol
from .service import Service, ServiceError
from .storage.db import Store


def create_app(settings: Settings | None = None, llm: LLMProvider | None = None,
               devices: DeviceManager | None = None,
               orchestrator_llm: LLMProvider | None = None,
               specialist_llm: LLMProvider | None = None,
               devin: DevinClientProtocol | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = Store(settings.db_path)
    service = Service(store, settings, Hub(store), llm=llm, devices=devices,
                      orchestrator_llm=orchestrator_llm, specialist_llm=specialist_llm, devin=devin)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        service.devices.shutdown()  # free the COM port and camera on exit

    app = FastAPI(title="inteGREAT API", version="0.2.0", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, e: ServiceError):
        return JSONResponse(status_code=e.status,
                            content={"error": {"code": e.code, "message": e.message, "details": e.details}})

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    app.include_router(router)
    app.include_router(visual_router)
    return app
