import json
import uuid
from datetime import datetime, timezone

import pytest
import requests
import responses
from django.core.cache.backends.locmem import LocMemCache

from invoicing.einvoicing.providers import OutgoingDocument, ProviderError
from invoicing.einvoicing.providers.sapi_sk import SapiSkProvider


BASE = 'https://ap.example/sapi'

DOCUMENT = OutgoingDocument(
    document_id='1780de4f-a87c-50cc-9d8a-f982abe36912',
    idempotency_key='5b0c6f1e-9a51-4a43-9d36-7a6f0f6e1c11',
    sender_id='0245:2020123456',
    receiver_id='0245:2021654321',
    document_type_id='urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##x::2.1',
    process_id='urn:fdc:peppol.eu:2017:poacc:billing:01:1.0',
    payload='<Invoice/>',
    checksum='a' * 64,
    created_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
)


def error(code, retryable=False, category='VALIDATION'):
    return {'error': {'category': category, 'code': code, 'message': f'{code} happened',
                      'retryable': retryable, 'correlation_id': 'corr-1'}}


def token(access='tok-1', refresh='ref-1', expires_in=900):
    return {'access_token': access, 'token_type': 'Bearer', 'expires_in': expires_in, 'refresh_token': refresh}


ACCEPTED = {'providerDocumentId': 'doc-1', 'status': 'ACCEPTED',
            'receivedAt': '2026-10-01T12:00:01Z', 'timestamp': '2026-10-01T12:00:01Z'}


@pytest.fixture
def provider():
    return SapiSkProvider(BASE, 'client', 'secret', environment='test', cache=LocMemCache(f'sapi-test-{uuid.uuid4()}', {}))  # locmem caches of one name share storage


@responses.activate
def test_submit(provider):
    responses.post(f'{BASE}/auth/token', json=token())
    send = responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    result = provider.submit(DOCUMENT)

    assert result.provider_document_id == 'doc-1'
    assert result.accepted
    assert result.received_at == datetime(2026, 10, 1, 12, 0, 1, tzinfo=timezone.utc)

    request = send.calls[0].request
    assert request.headers['Authorization'] == 'Bearer tok-1'
    assert request.headers['Idempotency-Key'] == DOCUMENT.idempotency_key
    assert request.headers['X-Peppol-Participant-Id'] == '0245:2020123456'
    body = json.loads(request.body)
    assert body['payload'] == '<Invoice/>'
    assert body['payloadFormat'] == 'XML'
    assert body['checksum'] == 'a' * 64
    assert body['metadata'] == {
        'documentId': DOCUMENT.document_id,
        'documentTypeId': DOCUMENT.document_type_id,
        'processId': DOCUMENT.process_id,
        'senderParticipantId': '0245:2020123456',
        'receiverParticipantId': '0245:2021654321',
        'creationDateTime': '2026-10-01T12:00:00+00:00',
    }

    auth = json.loads(responses.calls[0].request.body)
    assert auth == {'grant_type': 'client_credentials', 'client_id': 'client', 'client_secret': 'secret'}


@responses.activate
def test_token_is_reused(provider):
    responses.post(f'{BASE}/auth/token', json=token())
    responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    provider.submit(DOCUMENT)
    provider.submit(DOCUMENT)

    assert len([call for call in responses.calls if call.request.url.endswith('/auth/token')]) == 1


@responses.activate
def test_expired_token_is_renewed_with_rotated_refresh_token(provider):
    responses.post(f'{BASE}/auth/token', json=token(expires_in=30))  # within the expiry margin
    renew = responses.post(f'{BASE}/auth/renew', json=token(access='tok-2', refresh='ref-2'))
    responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    provider.submit(DOCUMENT)
    provider.submit(DOCUMENT)

    assert json.loads(renew.calls[0].request.body) == {'refresh_token': 'ref-1'}
    assert responses.calls[-1].request.headers['Authorization'] == 'Bearer tok-2'
    assert provider.cache.get(provider.token_cache_key)['refresh_token'] == 'ref-2'


@responses.activate
def test_invalid_refresh_token_falls_back_to_authenticating(provider):
    provider.cache.set(provider.token_cache_key, {'refresh_token': 'stale'})
    responses.post(f'{BASE}/auth/renew', json=error('SAPI-AUTH-001', category='AUTH'), status=401)
    responses.post(f'{BASE}/auth/token', json=token(access='tok-3'))
    responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    provider.submit(DOCUMENT)

    assert responses.calls[-1].request.headers['Authorization'] == 'Bearer tok-3'


@responses.activate
def test_token_without_refresh_token(provider):
    # the SAPI-SK 1.0 spec does not list refresh_token in the token response
    responses.post(f'{BASE}/auth/token', json={'access_token': 'tok-1', 'token_type': 'Bearer', 'expires_in': 30})
    responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    provider.submit(DOCUMENT)
    provider.submit(DOCUMENT)

    assert len([call for call in responses.calls if call.request.url.endswith('/auth/token')]) == 2


@responses.activate
def test_revoked_token_is_replaced_once(provider):
    responses.post(f'{BASE}/auth/token', json=token())
    responses.post(f'{BASE}/document/send', json=error('SAPI-AUTH-001', category='AUTH'), status=401)
    responses.post(f'{BASE}/auth/renew', json=token(access='tok-2', refresh='ref-2'))
    responses.post(f'{BASE}/document/send', json=ACCEPTED, status=202)

    assert provider.submit(DOCUMENT).provider_document_id == 'doc-1'
    assert responses.calls[-1].request.headers['Authorization'] == 'Bearer tok-2'


@pytest.mark.parametrize('status, body, code, retryable, outcome_unknown', [
    (400, error('SAPI-VAL-003'), 'SAPI-VAL-003', False, False),
    (402, error('SAPI-PROC-004', category='PROCESSING'), 'SAPI-PROC-004', False, False),
    (409, error('SAPI-PERM-002', category='PERMANENT'), 'SAPI-PERM-002', False, False),
    (429, error('SAPI-TEMP-002', retryable=True, category='TEMPORARY'), 'SAPI-TEMP-002', True, False),
    (502, error('SAPI-PROC-003', retryable=True, category='PROCESSING'), 'SAPI-PROC-003', True, True),
    # the body, not the HTTP status, decides
    (503, error('SAPI-PERM-001', retryable=False, category='PERMANENT'), 'SAPI-PERM-001', False, False),
    # gateway-shaped error
    (401, {'statusCode': 401, 'error': 'Unauthorized', 'message': 'Missing authentication'}, '', False, False),
    (504, None, '', True, True),
])
@responses.activate
def test_errors(provider, status, body, code, retryable, outcome_unknown):
    responses.post(f'{BASE}/auth/token', json=token())
    kwargs = {'json': body} if body is not None else {'body': 'Gateway Timeout'}
    responses.post(f'{BASE}/document/send', status=status, headers={'Retry-After': '7'}, **kwargs)
    if status == 401:
        # one retry with a renewed token, which is refused again
        responses.post(f'{BASE}/auth/renew', json=token(access='tok-2', refresh='ref-2'))

    with pytest.raises(ProviderError) as raised:
        provider.submit(DOCUMENT)

    assert raised.value.http_status == status
    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert raised.value.outcome_unknown is outcome_unknown
    assert raised.value.retry_after == 7


@responses.activate
def test_timeout_is_an_unknown_outcome(provider):
    responses.post(f'{BASE}/auth/token', json=token())
    responses.post(f'{BASE}/document/send', body=requests.ReadTimeout())

    with pytest.raises(ProviderError) as raised:
        provider.submit(DOCUMENT)

    assert raised.value.code == 'TIMEOUT'
    assert raised.value.retryable and raised.value.outcome_unknown


@responses.activate
def test_rejected_on_receipt(provider):
    responses.post(f'{BASE}/auth/token', json=token())
    responses.post(f'{BASE}/document/send', status=202,
                   json={'providerDocumentId': 'doc-9', 'status': 'REJECTED', 'timestamp': '2026-10-01T12:00:01Z'})

    result = provider.submit(DOCUMENT)

    assert not result.accepted
    assert result.received_at is None


@responses.activate
def test_health(provider):
    responses.get(f'{BASE}/health', json={'status': 'ok'})
    assert provider.health()

    responses.replace(responses.GET, f'{BASE}/health', json={'status': 'degraded'}, status=503)
    assert not provider.health()
