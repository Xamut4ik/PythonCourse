import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_client():
    def make(user=None):
        client = APIClient()
        if user is not None:
            token = RefreshToken.for_user(user).access_token
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client
    return make


@pytest.fixture
def admin(db):
    return UserFactory(username='admin', is_staff=True, is_superuser=True)


@pytest.fixture
def other_user(db):
    return UserFactory(username='other')


@pytest.fixture
def user_api(make_client, user):
    return make_client(user)


@pytest.fixture
def other_api(make_client, other_user):
    return make_client(other_user)


@pytest.fixture
def admin_api(make_client, admin):
    return make_client(admin)
