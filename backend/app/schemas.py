"""Compatibility facade for the API's domain-specific Pydantic schemas.

Existing imports can continue using ``app.schemas`` while individual schema
families live in smaller, focused modules.
"""
from .schema_types import *  # noqa: F401,F403
from .schemas_core import *  # noqa: F401,F403
from .schemas_workflows import *  # noqa: F401,F403
from .schemas_admin import *  # noqa: F401,F403
from .schemas_accounts import *  # noqa: F401,F403
