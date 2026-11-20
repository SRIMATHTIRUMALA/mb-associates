import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db_pool, close_db_pool
from app.routers import enquiries, staff

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mb_associates.main")

# Directory locations
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # d:/associate
BACKEND_DIR = Path(__file__).resolve().parent.parent     # d:/associate/backend
STATIC_DIR = BACKEND_DIR / "app" / "static"              # d:/associate/backend/app/static

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: startup and shutdown."""
    settings = get_settings()
    logger.info(f"Starting MB Associates Backend in {settings.environment} mode...")
    # Initialize connection pool if DATABASE_URL is configured
    await init_db_pool()
    yield
    # Shutdown
    logger.info("Shutting down MB Associates Backend...")
    await close_db_pool()

app = FastAPI(
    title="MB Associates Solar Project Assistance & Coordination Backend",
    description="Backend API and Staff Operations Queue for MB Associates Solar Website",
    version="1.0.0",
    lifespan=lifespan
)

settings = get_settings()

# Configure CORS for allowed origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin, "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount backend static files (/static/enquiry.js, etc.)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include Routers
app.include_router(enquiries.router)
app.include_router(staff.router)

# Whitelist of public frontend HTML pages to serve directly (NOT unrestricted static root)
FRONTEND_PAGES = {
    "": "index.html",
    "/": "index.html",
    "/index.html": "index.html",
    "/about": "about.html",
    "/about.html": "about.html",
    "/contact": "contact.html",
    "/contact.html": "contact.html",
    "/enquiry": "enquiry.html",
    "/enquiry.html": "enquiry.html",
    "/enquiry-confirmation": "enquiry-confirmation.html",
    "/enquiry-confirmation.html": "enquiry-confirmation.html",
    "/how-it-works": "how-it-works.html",
    "/how-it-works.html": "how-it-works.html",
    "/installation": "installation.html",
    "/installation.html": "installation.html",
    "/services": "services.html",
    "/services.html": "services.html",
    "/solar-calculator": "solar-calculator.html",
    "/solar-calculator.html": "solar-calculator.html",
    "/solutions": "solutions.html",
    "/solutions.html": "solutions.html",
    "/subsidy-finance": "subsidy-finance.html",
    "/subsidy-finance.html": "subsidy-finance.html",
}

for route_path, filename in FRONTEND_PAGES.items():
    file_path = BASE_DIR / filename

    def make_endpoint(target_file: Path):
        async def endpoint():
            if not target_file.exists():
                raise HTTPException(status_code=404, detail="Page not found")
            return FileResponse(path=str(target_file), media_type="text/html")
        return endpoint

    # Register endpoint for path (skip duplicate root)
    if route_path != "":
        app.add_api_route(
            route_path,
            make_endpoint(file_path),
            methods=["GET"],
            include_in_schema=False
        )

# Explicit route for the root
@app.get("/", include_in_schema=False)
async def serve_root():
    index_file = BASE_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(path=str(index_file), media_type="text/html")

# Explicit route for the original logo
@app.get("/mb-associates-logo.png", include_in_schema=False)
async def serve_logo():
    logo_file = BASE_DIR / "mb-associates-logo.png"
    if not logo_file.exists():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(path=str(logo_file), media_type="image/png")

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint providing status of API and database connection."""
    from app.db import get_pool
    pool = get_pool()
    db_status = "connected" if pool is not None else "disconnected_or_unconfigured"
    return {
        "status": "healthy",
        "service": "mb-associates-solar-backend",
        "database": db_status,
        "environment": settings.environment
    }
