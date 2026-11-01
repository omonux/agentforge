"""Payment-provider integration scaffold. Card data is always collected by hosted providers."""
import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

@router.get("/status")
def billing_status():
    return {
        "paystack_configured": bool(os.getenv("PAYSTACK_SECRET_KEY")),
        "opay_configured": all(os.getenv(k) for k in ("OPAY_PUBLIC_KEY", "OPAY_SECRET_KEY", "OPAY_MERCHANT_ID")),
        "live_payments_enabled": os.getenv("BILLING_LIVE_ENABLED", "false").lower() == "true",
        "customer_entitlements_enforced": False,
    }
