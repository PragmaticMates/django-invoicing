import hashlib
import hmac

from django.utils.timezone import now


def sign(body, secret, at=None):
    """(X-Webhook-Signature, X-Webhook-Timestamp) the way ePostman signs a notification."""
    timestamp = (at or now()).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    signature = hmac.new(secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256).hexdigest()
    return signature, timestamp
