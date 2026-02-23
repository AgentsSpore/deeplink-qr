from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl
from typing import Optional
import uuid
import json
from datetime import datetime
from user_agents import parse
import qrcode
import qrcode.constants
import io
import base64
from database import init_db, get_db, Link, ScanEvent
from sqlalchemy.orm import Session
from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="DeepLink QR", description="QR codes that actually work for Android deep links")

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize templates and static files
templates = Jinja2Templates(directory="templates")

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()

class LinkCreate(BaseModel):
    app_scheme: str
    app_package: str
    fallback_url: HttpUrl
    custom_path: Optional[str] = None
    title: Optional[str] = None

class LinkResponse(BaseModel):
    id: str
    short_url: str
    qr_code: str
    analytics_url: str

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard for creating QR codes"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/api/links", response_model=LinkResponse)
@limiter.limit("10/minute")
async def create_link(request: Request, link: LinkCreate, db: Session = Depends(get_db)):
    """Create a new deep link with QR code"""
    
    link_id = str(uuid.uuid4())[:8]
    
    # Build deep link URL
    deep_link = f"{link.app_scheme}://{link.custom_path or ''}"
    
    # Create database record
    db_link = Link(
        id=link_id,
        app_scheme=link.app_scheme,
        app_package=link.app_package,
        deep_link=deep_link,
        fallback_url=str(link.fallback_url),
        title=link.title or "Untitled Link",
        created_at=datetime.utcnow()
    )
    db.add(db_link)
    db.commit()
    
    # Generate QR code
    base_url = str(request.base_url).rstrip('/')
    redirect_url = f"{base_url}/r/{link_id}"
    
    # Use version=None for automatic version selection and ERROR_CORRECT_L
    # for lowest error correction (highest data capacity, supports up to ~7089 chars)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=5
    )
    qr.add_data(redirect_url)
    try:
        qr.make(fit=True)
    except qrcode.exceptions.DataOverflowError:
        raise HTTPException(
            status_code=400,
            detail="URL is too long to encode in a QR code. Please use a shorter URL."
        )
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return LinkResponse(
        id=link_id,
        short_url=redirect_url,
        qr_code=f"data:image/png;base64,{qr_base64}",
        analytics_url=f"{base_url}/analytics/{link_id}"
    )

@app.get("/r/{link_id}", response_class=HTMLResponse)
async def redirect_link(request: Request, link_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Smart redirect endpoint that handles deep linking"""
    
    db_link = db.query(Link).filter(Link.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Parse user agent
    ua_string = request.headers.get("user-agent", "")
    user_agent = parse(ua_string)
    
    # Determine device type
    if user_agent.is_mobile:
        if "android" in ua_string.lower():
            device_type = "android"
        elif "iphone" in ua_string.lower() or "ipad" in ua_string.lower():
            device_type = "ios"
        else:
            device_type = "mobile"
    else:
        device_type = "desktop"
    
    # Log scan event in background
    background_tasks.add_task(
        log_scan_event,
        db=db,
        link_id=link_id,
        user_agent=ua_string,
        ip_address=request.client.host,
        referrer=request.headers.get("referer", ""),
        device_type=device_type
    )
    
    return templates.TemplateResponse("smart_redirect.html", {
        "request": request,
        "link": db_link,
        "device_type": device_type,
        "deep_link": db_link.deep_link,
        "fallback_url": db_link.fallback_url,
        "app_package": db_link.app_package,
        "app_scheme": db_link.app_scheme,
    })

def log_scan_event(db: Session, link_id: str, user_agent: str, ip_address: str, referrer: str, device_type: str):
    """Log a scan event to the database"""
    event = ScanEvent(
        id=str(uuid.uuid4()),
        link_id=link_id,
        user_agent=user_agent,
        ip_address=ip_address,
        referrer=referrer,
        device_type=device_type,
        timestamp=datetime.utcnow()
    )
    db.add(event)
    db.commit()

@app.get("/analytics/{link_id}", response_class=HTMLResponse)
async def analytics_page(request: Request, link_id: str, db: Session = Depends(get_db)):
    """Analytics dashboard for a specific link"""
    
    db_link = db.query(Link).filter(Link.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    events = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    # Calculate device breakdown
    device_counts = {"android": 0, "ios": 0, "desktop": 0, "mobile": 0}
    for event in events:
        device_type = event.device_type or "desktop"
        if device_type in device_counts:
            device_counts[device_type] += 1
        else:
            device_counts["desktop"] += 1
    
    total_scans = len(events)
    
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "link": db_link,
        "events": events,
        "device_counts": device_counts,
        "total_scans": total_scans,
    })

@app.get("/api/analytics/{link_id}")
async def get_analytics(link_id: str, db: Session = Depends(get_db)):
    """Get analytics data for a link"""
    
    db_link = db.query(Link).filter(Link.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    events = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    device_counts = {"android": 0, "ios": 0, "desktop": 0, "mobile": 0}
    for event in events:
        device_type = event.device_type or "desktop"
        if device_type in device_counts:
            device_counts[device_type] += 1
    
    return {
        "link_id": link_id,
        "total_scans": len(events),
        "device_breakdown": device_counts,
        "created_at": db_link.created_at.isoformat(),
        "deep_link": db_link.deep_link,
        "fallback_url": db_link.fallback_url,
    }

@app.get("/sdk/android", response_class=HTMLResponse)
async def sdk_android(request: Request):
    """Android SDK documentation page"""
    return templates.TemplateResponse("sdk_android.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    import os
    from dotenv import load_dotenv
    load_dotenv()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=host, port=port)
