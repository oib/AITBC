"""
UI router for serving static HTML pages
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["ui"])

# Get templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=templates_dir)


@router.get("/services", response_class=HTMLResponse, include_in_schema=False)
async def services_ui(request: Request) -> HTMLResponse:
    """Serve the service configuration UI"""
    return templates.TemplateResponse(request, "services.html", {"request": request})
