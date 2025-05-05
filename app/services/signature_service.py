import hashlib
import hmac
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app.models.settings import settings

class SignatureService:
    def __init__(self, secret_key: str, expiration_seconds: int):
        self.secret_key = secret_key.encode('utf-8')
        self.expiration_seconds = expiration_seconds

    def _generate_signature(self, path: str, expiry: int) -> str:
        """Generates a signature for the given path and expiry time."""
        message = f"{path}:{expiry}".encode('utf-8')
        signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        return signature

    def sign_url(self, base_url: str, path: str) -> str:
        """Adds expiry and signature parameters to a URL path relative to the base URL."""
        expiry = int(time.time()) + self.expiration_seconds
        signature = self._generate_signature(path, expiry)

        # Construct the full URL with query parameters
        # Assuming the base_url doesn't have query params itself
        # And path starts with '/' if it's relative to the base_url root
        if not path.startswith('/'):
             path = '/' + path

        query_params = urlencode({'expiry': expiry, 'signature': signature})
        signed_path = f"{path}?{query_params}"

        # Combine base_url and signed_path carefully
        base_parts = urlparse(base_url)
        # Ensure base path ends with a slash if it's not just the domain
        base_path = base_parts.path
        if base_path and not base_path.endswith('/'):
            base_path += '/'
        elif not base_path:
            base_path = '/'

        # Avoid double slashes if path already starts with one
        final_path = base_path.rstrip('/') + path

        final_url_parts = base_parts._replace(path=final_path, query=query_params)
        return urlunparse(final_url_parts)


    def verify_signature(self, path: str, query_params: dict) -> bool:
        """Verifies the signature and expiry from query parameters for a given path."""
        try:
            expiry = int(query_params.get('expiry', ['0'])[0])
            provided_signature = query_params.get('signature', [''])[0]
        except (ValueError, IndexError):
            return False # Malformed query params

        if not provided_signature or time.time() > expiry:
            return False # Missing signature or expired

        expected_signature = self._generate_signature(path, expiry)
        return hmac.compare_digest(expected_signature, provided_signature)

# Singleton instance
signature_service = SignatureService(
    secret_key=settings.SIGNATURE_SECRET_KEY,
    expiration_seconds=settings.SIGNATURE_EXPIRATION_SECONDS
) 