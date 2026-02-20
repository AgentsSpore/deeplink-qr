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
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(redirect_url)
    qr.make(fit=True)
    
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

@app.get("/r/{link_id}")
@limiter.limit("100/minute")
async def redirect_link(request: Request, link_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Smart redirect endpoint with browser detection and fallback handling"""
    
    # Get link from database
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Parse user agent
    user_agent_string = request.headers.get("user-agent", "")
    user_agent = parse(user_agent_string)
    
    # Determine device type
    if user_agent.is_mobile:
        if user_agent.os.family == "Android":
            device_type = "android"
        elif user_agent.os.family == "iOS":
            device_type = "ios"
        else:
            device_type = "mobile_other"
    else:
        device_type = "desktop"
    
    # Log analytics
    background_tasks.add_task(
        log_scan_event,
        db,
        link_id,
        user_agent_string,
        request.client.host if request.client else "unknown",
        request.headers.get("referer"),
        device_type
    )
    
    # Android: Use smart redirect template
    if device_type == "android":
        return templates.TemplateResponse("smart_redirect.html", {
            "request": request,
            "deep_link": link.deep_link,
            "fallback_url": link.fallback_url,
            "app_package": link.app_package,
            "app_scheme": link.app_scheme
        })
    
    # iOS: Redirect to deep link (will fallback via Universal Links)
    elif device_type == "ios":
        return RedirectResponse(url=link.deep_link)
    
    # Desktop or other: Redirect to fallback URL
    else:
        return RedirectResponse(url=link.fallback_url)

def log_scan_event(db: Session, link_id: str, user_agent: str, ip_address: str, referrer: Optional[str], device_type: str):
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
async def analytics_page(link_id: str, request: Request, db: Session = Depends(get_db)):
    """Analytics dashboard for a specific link"""
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Get all scan events
    events = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    # Calculate statistics
    total_scans = len(events)
    device_counts = {"android": 0, "ios": 0, "desktop": 0, "mobile_other": 0}
    
    for event in events:
        device_type = event.device_type or "desktop"
        if device_type in device_counts:
            device_counts[device_type] += 1
    
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "link": link,
        "total_scans": total_scans,
        "device_counts": device_counts,
        "recent_scans": events[-10:][::-1]  # Last 10 scans, reversed
    })

@app.get("/api/analytics/{link_id}")
async def analytics_api(link_id: str, db: Session = Depends(get_db)):
    """Get analytics data as JSON"""
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    events = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    device_counts = {"android": 0, "ios": 0, "desktop": 0, "mobile_other": 0}
    for event in events:
        device_type = event.device_type or "desktop"
        if device_type in device_counts:
            device_counts[device_type] += 1
    
    return {
        "link_id": link_id,
        "total_scans": len(events),
        "device_breakdown": device_counts,
        "created_at": link.created_at.isoformat(),
        "deep_link": link.deep_link,
        "fallback_url": link.fallback_url
    }

@app.get("/sdk/android")
async def sdk_android(request: Request):
    """Android SDK documentation page"""
    return templates.TemplateResponse("sdk_android.html", {"request": request})
