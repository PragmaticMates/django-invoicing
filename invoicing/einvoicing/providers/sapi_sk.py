"""
SAPI-SK 1.0 (Standardised Access Point Interface, Slovakia): the API Slovak
Digital Postmen expose for sending documents into Peppol, published by the
Slovak OpenPeppol community at https://www.sapi-sk.sk/openapi.json.

Generic: nothing here is specific to one Digital Postman. ``base_url`` is the
provider's SAPI base, e.g. ``https://<provider host>/sapi``.

SAPI-SK 1.0 has no call for the status of a sent document, nor for
validation; providers which offer those outside SAPI can subclass this.
"""
import hashlib
import time

import requests
from django.core.cache import cache as default_cache
from django.utils.dateparse import parse_datetime

from invoicing.einvoicing.providers.base import EInvoiceProvider, ProviderError, SubmitResult


# HTTP statuses which mean "try again later" when the body says nothing better
RETRYABLE_HTTP_STATUSES = frozenset({429, 502, 503, 504})

# Renew the access token this long before it expires
TOKEN_EXPIRY_MARGIN = 60


class SapiSkProvider(EInvoiceProvider):
    name = 'sapi-sk'

    def __init__(self, base_url, client_id, client_secret, *, environment='', timeout=30, session=None, cache=None):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.environment = environment
        self.timeout = timeout
        self.session = session or requests.Session()
        self.cache = cache or default_cache

    # HTTP

    def request(self, method, path, *, json=None, headers=None, authenticated=True, retry_unauthorized=True):
        all_headers = {'Accept': 'application/json', **(headers or {})}

        if authenticated:
            all_headers['Authorization'] = f'Bearer {self.get_access_token()}'

        try:
            response = self.session.request(method, f'{self.base_url}{path}', json=json, headers=all_headers,
                                            timeout=self.timeout)
        except requests.ConnectionError as error:
            # Covers connect timeouts too: the request may or may not have left
            raise ProviderError(f'Cannot reach {self.base_url}: {error}', code='CONNECTION',
                                retryable=True, outcome_unknown=True) from error
        except requests.Timeout as error:
            raise ProviderError(f'No response from {self.base_url} in {self.timeout}s', code='TIMEOUT',
                                retryable=True, outcome_unknown=True) from error

        if response.status_code == 401 and authenticated and retry_unauthorized:
            # the cached token may have been revoked or expired early
            self.forget_tokens()
            return self.request(method, path, json=json, headers=headers, authenticated=True, retry_unauthorized=False)

        if response.status_code >= 400:
            raise self.error_from_response(response)

        return response

    def error_from_response(self, response):
        try:
            body = response.json()
        except ValueError:
            body = None

        retry_after = response.headers.get('Retry-After')
        retry_after = int(retry_after) if retry_after and retry_after.isdigit() else None
        default_retryable = response.status_code in RETRYABLE_HTTP_STATUSES

        if isinstance(body, dict) and isinstance(body.get('error'), dict):
            # SAPI-SK error envelope
            error = body['error']
            retryable = bool(error.get('retryable', default_retryable))
            return ProviderError(
                error.get('message') or f'HTTP {response.status_code}',
                code=error.get('code', ''),
                retryable=retryable,
                outcome_unknown=response.status_code >= 500 and retryable,
                http_status=response.status_code,
                correlation_id=error.get('correlation_id', ''),
                details=error.get('details') or [],
                retry_after=retry_after,
                raw=body,
            )

        # Some gateways answer in a different shape, e.g. {statusCode, error, message, code}
        message = (body or {}).get('message') if isinstance(body, dict) else None
        return ProviderError(
            message or f'HTTP {response.status_code}: {response.text[:500]}',
            code=(body or {}).get('code', '') if isinstance(body, dict) else '',
            retryable=default_retryable,
            outcome_unknown=response.status_code >= 500,
            http_status=response.status_code,
            retry_after=retry_after,
            raw=body if isinstance(body, dict) else None,
        )

    # Tokens

    @property
    def token_cache_key(self):
        digest = hashlib.sha256(f'{self.base_url}|{self.client_id}'.encode()).hexdigest()[:32]
        return f'invoicing:einvoicing:sapi-sk:token:{digest}'

    def forget_tokens(self):
        tokens = self.cache.get(self.token_cache_key) or {}
        # keep the refresh token: renewing is cheaper than authenticating again
        self.cache.set(self.token_cache_key, {'refresh_token': tokens.get('refresh_token')}, None)

    def store_tokens(self, data, previous_refresh_token=None):
        tokens = {
            'access_token': data['access_token'],
            'expires_at': time.time() + int(data.get('expires_in', 900)),
            # Refresh tokens rotate: keep the newest one, or the old one if none came back
            'refresh_token': data.get('refresh_token') or previous_refresh_token,
        }
        self.cache.set(self.token_cache_key, tokens, None)
        return tokens['access_token']

    def get_access_token(self):
        tokens = self.cache.get(self.token_cache_key) or {}

        if tokens.get('access_token') and tokens.get('expires_at', 0) - TOKEN_EXPIRY_MARGIN > time.time():
            return tokens['access_token']

        if tokens.get('refresh_token'):
            try:
                response = self.request('POST', '/auth/renew', json={'refresh_token': tokens['refresh_token']},
                                        authenticated=False)
                return self.store_tokens(response.json(), tokens['refresh_token'])
            except ProviderError as error:
                if error.retryable:
                    raise
                # invalid, expired or revoked refresh token: authenticate from scratch

        response = self.request('POST', '/auth/token', authenticated=False, json={
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        })
        return self.store_tokens(response.json())

    # API

    def submit(self, document):
        response = self.request('POST', '/document/send', headers={
            'Idempotency-Key': document.idempotency_key,
            'X-Peppol-Participant-Id': document.sender_id,
        }, json={
            'metadata': {
                'documentId': document.document_id,
                'documentTypeId': document.document_type_id,
                'processId': document.process_id,
                'senderParticipantId': document.sender_id,
                'receiverParticipantId': document.receiver_id,
                'creationDateTime': document.created_at.isoformat(),
            },
            'payload': document.payload,
            'payloadFormat': 'XML',
            'payloadEncoding': 'UTF-8',
            'checksum': document.checksum,
        })

        data = response.json()
        return SubmitResult(
            provider_document_id=data.get('providerDocumentId', ''),
            accepted=data.get('status') == 'ACCEPTED',
            received_at=parse_datetime(data['receivedAt']) if data.get('receivedAt') else None,
            raw=data,
        )

    def health(self):
        """True when the provider reports itself healthy."""
        try:
            response = self.request('GET', '/health', authenticated=False)
        except ProviderError:
            return False
        return response.json().get('status') == 'ok'
