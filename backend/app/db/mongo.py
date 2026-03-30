from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import os
import certifi

_client: AsyncIOMotorClient | None = None

async def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        client_kwargs = {}
        # Ensure TLS CA is available for Atlas connections
        if "mongodb+srv://" in settings.mongodb_uri or "tls=true" in settings.mongodb_uri:
            client_kwargs["tls"] = True
            client_kwargs["tlsCAFile"] = certifi.where()
            if os.getenv("MONGODB_TLS_ALLOW_INVALID", "").lower() in ("1", "true", "yes"):
                client_kwargs["tlsAllowInvalidCertificates"] = True
                client_kwargs["tlsAllowInvalidHostnames"] = True
        _client = AsyncIOMotorClient(settings.mongodb_uri, **client_kwargs)
    return _client

async def get_db():
    client = await get_client()
    return client[settings.mongodb_db]
