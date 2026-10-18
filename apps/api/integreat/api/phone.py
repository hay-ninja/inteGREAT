"""Restricted LAN HTTPS surface: capture page and paired frame uploads only."""
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response

from ..observations.browser_camera import BrowserCamera, MAX_UPLOAD
from ..observations.camera_adapter import CameraError


def create_phone_app(camera_manager) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "Permissions-Policy": "camera=(self), microphone=()",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src blob:; frame-ancestors 'none'; base-uri 'none'"})
        return response

    assets = Path(__file__).with_name("phone_assets")
    @app.get("/phone")
    def page():
        return FileResponse(assets / "index.html", media_type="text/html")

    @app.get("/phone/capture.js")
    def script():
        return FileResponse(assets / "capture.js", media_type="text/javascript")

    @app.get("/phone/style.css")
    def style():
        return FileResponse(assets / "style.css", media_type="text/css")

    def paired(request):
        camera = camera_manager.source
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not isinstance(camera, BrowserCamera) or not camera.authorized(token):
            raise HTTPException(401, "Pairing expired, released, or invalid. Create a new link on the laptop.")
        return camera

    @app.post("/phone/frame")
    async def upload(request: Request):
        camera = paired(request)
        if request.headers.get("content-type") != "image/jpeg":
            raise HTTPException(415, "Expected image/jpeg")
        async def read():
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_UPLOAD:
                    raise HTTPException(413, "Frame too large")
            return bytes(data)
        try:
            data = await asyncio.wait_for(read(), 5)
            await asyncio.to_thread(camera.accept, data)
        except TimeoutError:
            raise HTTPException(408, "Frame upload timed out")
        except CameraError as exc:
            raise HTTPException(422, str(exc))
        return Response(status_code=204)

    @app.delete("/phone/session")
    def stop(request: Request):
        paired(request).release()
        return Response(status_code=204)

    return app
