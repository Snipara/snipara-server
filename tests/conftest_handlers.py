"""Pytest configuration for handler tests.

Handler tests patch their external service calls directly. This module only
sets required environment variables before imports and must not replace
``src.*`` modules in ``sys.modules`` because that leaks mocks across the full
test suite during collection.
"""

import os

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["NEON_DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["NEXTAUTH_SECRET"] = "test-secret"
