"""Shared database infrastructure for CELINE projects.

This package centralizes SQLAlchemy engine/session creation and DB initialization.
"""
from .engine import get_async_engine
from .session import get_async_sessionmaker
