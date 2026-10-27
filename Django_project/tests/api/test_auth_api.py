import pytest
from rest_framework.throttling import AnonRateThrottle

from tests.factories import PASSWORD

pytestmark = [pytest.mark.api, pytest.mark.django_db]


def obtain(api_client, username, password=PASSWORD):
    return api_client.post('/api/token/', {'username': username, 'password': password}, format='json')


def test_obtain_token_pair(api_client, user):
    response = obtain(api_client, user.username)
    assert response.status_code == 200
    assert {'access', 'refresh'} <= response.data.keys()


def test_obtain_token_with_wrong_password(api_client, user):
    response = obtain(api_client, user.username, 'wrong-password')
    assert response.status_code == 401


def test_refresh_token(api_client, user):
    refresh = obtain(api_client, user.username).data['refresh']
    response = api_client.post('/api/token/refresh/', {'refresh': refresh}, format='json')
    assert response.status_code == 200
    assert 'access' in response.data


def test_refresh_with_invalid_token(api_client):
    response = api_client.post('/api/token/refresh/', {'refresh': 'invalid'}, format='json')
    assert response.status_code == 401


def test_verify_token(api_client, user):
    access = obtain(api_client, user.username).data['access']
    assert api_client.post('/api/token/verify/', {'token': access}, format='json').status_code == 200
    assert api_client.post('/api/token/verify/', {'token': access + 'x'}, format='json').status_code == 401


def test_protected_endpoint_requires_token(api_client):
    assert api_client.get('/api/orders/').status_code == 401


def test_protected_endpoint_with_bearer_token(api_client, user):
    access = obtain(api_client, user.username).data['access']
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    response = api_client.get('/api/orders/')
    assert response.status_code == 200
    assert response.data['results'] == []


def test_invalid_bearer_token_is_rejected(api_client):
    api_client.credentials(HTTP_AUTHORIZATION='Bearer broken')
    assert api_client.get('/api/books/').status_code == 401


def test_anonymous_requests_are_throttled(api_client, mocker):
    mocker.patch.object(AnonRateThrottle, 'THROTTLE_RATES', {'anon': '3/minute'})
    statuses = [api_client.get('/api/books/').status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


@pytest.mark.parametrize('url', ['/api/schema/', '/api/docs/', '/api/redoc/'])
def test_api_documentation_is_available(api_client, url):
    assert api_client.get(url).status_code == 200


def test_cors_allows_local_frontend(api_client):
    response = api_client.get('/api/books/', HTTP_ORIGIN='http://localhost:3000')
    assert response['Access-Control-Allow-Origin'] == 'http://localhost:3000'


def test_cors_rejects_unknown_origin(api_client):
    response = api_client.get('/api/books/', HTTP_ORIGIN='http://evil.example.com')
    assert 'Access-Control-Allow-Origin' not in response
