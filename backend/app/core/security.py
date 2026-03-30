from typing import Any, Dict
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
import httpx
import time

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_cache: Dict[str, Any] | None = None
_jwks_cache_exp: float = 0

async def _get_jwks() -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_exp
    now = time.time()
    if _jwks_cache and _jwks_cache_exp > now:
        return _jwks_cache
    if not settings.kinde_issuer_url:
        raise HTTPException(status_code=500, detail="KINDE_ISSUER_URL not configured")

    jwks_url = settings.kinde_issuer_url.rstrip("/") + "/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_exp = now + 3600
        return _jwks_cache

async def _decode_token(token: str) -> Dict[str, Any]:
    jwks = await _get_jwks()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    kid = unverified_header.get("kid")
    key = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            key = jwk
            break
    if not key:
        raise HTTPException(status_code=401, detail="Invalid token key")

    options = {"verify_aud": bool(settings.kinde_audience or settings.kinde_client_id)}
    audience = settings.kinde_audience or settings.kinde_client_id or None
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.kinde_issuer_url,
            audience=audience,
            options=options,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    payload = await _decode_token(credentials.credentials)
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "given_name": payload.get("given_name") or payload.get("given_name"),
        "family_name": payload.get("family_name") or payload.get("family_name"),
        "picture": payload.get("picture"),
    }

# Optional auth for dev flows: returns None when no token is provided.
async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = await _decode_token(credentials.credentials)
    except HTTPException:
        return None
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "given_name": payload.get("given_name") or payload.get("given_name"),
        "family_name": payload.get("family_name") or payload.get("family_name"),
        "picture": payload.get("picture"),
    }
