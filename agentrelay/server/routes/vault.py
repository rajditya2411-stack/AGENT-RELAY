"""
AgentRelay v2.0 — Local BYOK Encrypted Vault Router
Zero-trust credential storage using AES-256-GCM.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentrelay.server.context import ServerContext

router = APIRouter(prefix="/api/v2/vault", tags=["Vault"])


class UnlockVaultRequest(BaseModel):
    passphrase: str = Field(..., description="Master passphrase to unlock encrypted vault")


class StoreKeyRequest(BaseModel):
    provider: str = Field(..., description="Provider: 'xai', 'openai', 'anthropic', 'meta_graph', or custom")
    key: str = Field(..., description="Secret API key or token")
    rotate: bool = Field(default=False, description="Whether to rotate if key already exists")


@router.get("/status")
async def get_vault_status():
    """Get lock status and list of configured provider credentials without exposing raw keys."""
    ctx = ServerContext.get_instance()
    configured = ctx.vault.list_configured_providers()
    return {
        "isLocked": ctx.vault.is_locked,
        "vaultPath": str(ctx.vault.vault_path),
        "configuredProviders": configured,
        "providerCount": len(configured),
    }


@router.post("/unlock")
async def unlock_vault(request: UnlockVaultRequest):
    """Unlock encrypted vault using passphrase."""
    ctx = ServerContext.get_instance()
    try:
        success = ctx.vault.unlock(request.passphrase)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to unlock vault: {e}")

    # Re-sync keys with active adapters
    if success:
        ctx._init_adapters()

    return {"status": "SUCCESS", "message": "Vault unlocked successfully.", "isLocked": ctx.vault.is_locked}


@router.post("/lock")
async def lock_vault():
    """Zero in-memory credentials and lock the vault."""
    ctx = ServerContext.get_instance()
    ctx.vault.lock()
    return {"status": "SUCCESS", "message": "Vault locked. In-memory keys cleared.", "isLocked": True}


@router.post("/keys")
async def store_or_rotate_key(request: StoreKeyRequest):
    """Store or rotate an encrypted provider API key."""
    ctx = ServerContext.get_instance()
    if ctx.vault.is_locked:
        raise HTTPException(status_code=403, detail="Vault is locked. Unlock before modifying keys.")

    provider = request.provider.lower().strip()
    if request.rotate and provider in ctx.vault.list_configured_providers():
        ctx.vault.rotate_key(provider, request.key)
        action_msg = f"Rotated key for provider '{provider}'"
    else:
        ctx.vault.set_key(provider, request.key)
        action_msg = f"Stored key for provider '{provider}'"

    # Propagate to active adapters
    if provider == "xai" and "grokbot" in ctx.adapters:
        ctx.adapters["grokbot"].api_key = request.key
        ctx.adapters["grokbot"].mock_mode = False
    elif provider == "openai" and "dots" in ctx.adapters:
        ctx.adapters["dots"].api_key = request.key
        ctx.adapters["dots"].mock_mode = False
    elif provider == "meta_graph" and "muse" in ctx.adapters:
        ctx.adapters["muse"].access_token = request.key
        ctx.adapters["muse"].mock_mode = False

    # Audit log (no key leakage!)
    ctx.audit_logger.record(
        agent_id="mobile_user",
        action_type="VAULT_KEY_UPDATE",
        target=f"vault/{provider}",
        payload={"provider": provider, "rotated": request.rotate},
        status="EXECUTED",
        severity="INFO",
    )

    return {"status": "SUCCESS", "message": action_msg, "configuredProviders": ctx.vault.list_configured_providers()}


@router.delete("/keys/{provider}")
async def delete_key(provider: str):
    """Remove a provider API key from the vault."""
    ctx = ServerContext.get_instance()
    if ctx.vault.is_locked:
        raise HTTPException(status_code=403, detail="Vault is locked.")

    cleared = ctx.vault.clear_key(provider.lower().strip())
    return {"status": "SUCCESS", "cleared": cleared, "configuredProviders": ctx.vault.list_configured_providers()}


@router.post("/wipe")
async def wipe_vault():
    """Emergency wipe of all credentials in memory and on disk."""
    ctx = ServerContext.get_instance()
    ctx.vault.wipe_all()

    # Reset adapters to mock mode
    for adapter in ctx.adapters.values():
        adapter.mock_mode = True

    ctx.audit_logger.record(
        agent_id="mobile_user",
        action_type="VAULT_EMERGENCY_WIPE",
        target="vault",
        payload={"action": "ALL_KEYS_WIPED"},
        status="EXECUTED",
        severity="CRITICAL",
    )

    return {"status": "SUCCESS", "message": "All vault credentials wiped securely."}
