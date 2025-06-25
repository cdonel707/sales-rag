from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import json

Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    slack_channel_id = Column(String, index=True)
    slack_thread_ts = Column(String, index=True, nullable=True)
    slack_user_id = Column(String, index=True)
    question = Column(Text)
    answer = Column(Text)
    sources = Column(Text)  # JSON string of sources used
    created_at = Column(DateTime, default=datetime.utcnow)

class SalesforceDocument(Base):
    __tablename__ = "salesforce_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    sf_object_type = Column(String, index=True)  # Account, Opportunity, Contact, etc.
    sf_object_id = Column(String, unique=True, index=True)
    title = Column(String)
    content = Column(Text)
    doc_metadata = Column(Text)  # JSON string of additional metadata
    last_updated = Column(DateTime, default=datetime.utcnow)
    is_embedded = Column(Boolean, default=False)

class SlackDocument(Base):
    __tablename__ = "slack_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, index=True)
    message_ts = Column(String, unique=True, index=True)
    thread_ts = Column(String, index=True, nullable=True)
    user_id = Column(String, index=True)
    content = Column(Text)
    doc_metadata = Column(Text)  # JSON string of additional metadata
    created_at = Column(DateTime)
    is_embedded = Column(Boolean, default=False)

def create_database(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    return engine

def get_session_maker(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine) 