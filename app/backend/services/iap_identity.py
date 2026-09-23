import logging
import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

AUDIENCE_ENV_VAR = "IAP_AUDIENCE"
IAP_JWT_HEADER = "x-goog-iap-jwt-assertion"
CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"


def verify_iap_identity(jwt_assertion: str) -> str | None:
    """Verifies the signature of an X-Goog-IAP-JWT-Assertion header value and
    returns the authenticated caller's email, for logging only — access
    control itself is already fully enforced by IAP before the request
    reaches this app. Returns None (never raises) if IAP_AUDIENCE isn't
    configured (e.g. local dev, where IAP doesn't run) or verification
    fails for any reason."""
    audience = os.environ.get(AUDIENCE_ENV_VAR)
    if not audience:
        return None
    try:
        decoded = id_token.verify_token(
            jwt_assertion,
            google_requests.Request(),
            audience=audience,
            certs_url=CERTS_URL,
        )
        return decoded.get("email")
    except Exception:
        logger.warning("Failed to verify IAP identity JWT", exc_info=True)
        return None
