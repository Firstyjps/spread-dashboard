"""Shared slowapi Limiter — imported by both main.py and routes that need decorators.

Avoids the circular import you'd get if routes did `from app.main import limiter`.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
