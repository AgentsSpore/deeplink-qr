from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class Link(Base):
    __tablename__ = "links"
    
    id = Column(String, primary_key=True)
    app_scheme = Column(String, nullable=False)
    app_package = Column(String, nullable=False)
    deep_link = Column(String, nullable=False)
    fallback_url = Column(String, nullable=False)
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScanEvent(Base):
    __tablename__ = "scan_events"
    
    id = Column(String, primary_key=True)
    link_id = Column(String, nullable=False)
    user_agent = Column(Text)
    ip_address = Column(String)
    referrer = Column(String)
    device_type = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

engine = create_engine("sqlite:///./deeplink_qr.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
