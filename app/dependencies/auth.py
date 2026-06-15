from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.settings import get_settings

settings = get_settings()

api_key_header = APIKeyHeader(name=settings.auth_header_name, auto_error=True)


async def validate_developer_token(api_key: str = Security(api_key_header)) -> str:
    if not api_key.startswith(settings.dev_token_prefix):
        raise HTTPException(
            status_code=403, detail="Invalid developer token structure."
        )
    return api_key
