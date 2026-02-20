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

app = FastAPI(title="DeepLink QR", description="QR codes that actually work for Android deep links")

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
async def create_link(link: LinkCreate, request: Request, db: Session = Depends(get_db)):
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
async def redirect_link(link_id: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Smart redirect endpoint with browser detection and fallback handling"""
    
    # Get link from database
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Parse user agent
    user_agent_string = request.headers.get('user-agent', '')
    user_agent = parse(user_agent_string)
    
    # Determine device type
    is_android = user_agent.os.family == 'Android'
    is_ios = user_agent.os.family == 'iOS'
    is_mobile = user_agent.is_mobile
    
    # Record analytics in background
    background_tasks.add_task(
        record_scan,
        link_id=link_id,
        user_agent=user_agent_string,
        ip_address=request.client.host,
        referrer=request.headers.get('referer'),
        device_type='android' if is_android else ('ios' if is_ios else 'desktop')
    )
    
    # Strategy 1: Android with app likely installed - try deep link directly
    if is_android:
        # Return HTML with intent fallback logic
        return templates.TemplateResponse("smart_redirect.html", {
            "request": request,
            "app_scheme": link.app_scheme,
            "deep_link": link.deep_link,
            "fallback_url": link.fallback_url,
            "app_package": link.app_package,
            "is_android": True,
            "is_ios": False
        })
    
    # Strategy 2: iOS - use universal link pattern
    if is_ios:
        return templates.TemplateResponse("smart_redirect.html", {
            "request": request,
            "app_scheme": link.app_scheme,
            "deep_link": link.deep_link,
            "fallback_url": link.fallback_url,
            "app_package": link.app_package,
            "is_android": False,
            "is_ios": True
        })
    
    # Strategy 3: Desktop or unknown - go to fallback (Play Store or web)
    return RedirectResponse(url=link.fallback_url)

@app.get("/analytics/{link_id}", response_class=HTMLResponse)
async def analytics_dashboard(link_id: str, request: Request, db: Session = Depends(get_db)):
    """Analytics dashboard for a link"""
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Get scan statistics
    scans = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    total_scans = len(scans)
    android_scans = len([s for s in scans if s.device_type == 'android'])
    ios_scans = len([s for s in scans if s.device_type == 'ios'])
    desktop_scans = len([s for s in scans if s.device_type == 'desktop'])
    
    # Recent scans
    recent_scans = scans[-10:] if scans else []
    
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "link": link,
        "total_scans": total_scans,
        "android_scans": android_scans,
        "ios_scans": ios_scans,
        "desktop_scans": desktop_scans,
        "recent_scans": recent_scans
    })

@app.get("/api/analytics/{link_id}")
async def get_analytics_api(link_id: str, db: Session = Depends(get_db)):
    """API endpoint for analytics data"""
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    scans = db.query(ScanEvent).filter(ScanEvent.link_id == link_id).all()
    
    return {
        "link_id": link_id,
        "total_scans": len(scans),
        "by_device": {
            "android": len([s for s in scans if s.device_type == 'android']),
            "ios": len([s for s in scans if s.device_type == 'ios']),
            "desktop": len([s for s in scans if s.device_type == 'desktop'])
        },
        "scans": [
            {
                "timestamp": s.timestamp.isoformat(),
                "device_type": s.device_type,
                "ip_address": s.ip_address
            }
            for s in scans[-50:]
        ]
    }

def record_scan(link_id: str, user_agent: str, ip_address: str, referrer: Optional[str], device_type: str):
    """Record a scan event in the database"""
    db = next(get_db())
    try:
        event = ScanEvent(
            link_id=link_id,
            user_agent=user_agent,
            ip_address=ip_address,
            referrer=referrer,
            device_type=device_type,
            timestamp=datetime.utcnow()
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

@app.get("/sdk/android")
async def android_sdk_docs(request: Request):
    """Documentation for Android SDK"""
    return templates.TemplateResponse("sdk_android.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "deeplink-qr"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
