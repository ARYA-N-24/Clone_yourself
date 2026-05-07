"""
Shared SlowAPI rate limiter instance.

Defined here (not in main.py) so that API route modules can import it
without creating a circular dependency with backend.main.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
