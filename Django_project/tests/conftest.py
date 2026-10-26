from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from django.utils import translation

from tests.factories import BookFactory, CategoryFactory, GroupFactory, UserFactory

ORDER_DATA = {
    'first_name': 'Тарас',
    'last_name': 'Шевченко',
    'email': 'taras@example.com',
    'address': 'вул. Хрещатик, 1',
    'city': 'Київ',
}

BOOK_PERMISSIONS = ['add_book', 'change_book', 'delete_book']


@pytest.fixture(autouse=True)
def default_language():
    # LocaleMiddleware не скидає мову після запиту — без цього reverse() у наступному тесті міг би дати /en/
    translation.activate('uk')
    yield
    translation.deactivate()


@pytest.fixture
def category(db):
    return CategoryFactory(name='Класика', slug='classic')


@pytest.fixture
def book(category):
    return BookFactory(title='Кобзар', author='Шевченко', price=Decimal('250.50'), stock=5, category=category)


@pytest.fixture
def book2(category):
    return BookFactory(
        title='Тіні забутих предків', author='Коцюбинський', price=Decimal('180.00'), stock=1, category=category,
    )


@pytest.fixture
def user(db):
    return UserFactory(username='taras', email='taras@example.com')


@pytest.fixture
def manager(db):
    group = GroupFactory(name='Менеджери', permissions=BOOK_PERMISSIONS)
    manager = UserFactory(username='manager')
    manager.groups.add(group)
    return manager


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def manager_client(client, manager):
    client.force_login(manager)
    return client


@pytest.fixture
def add_to_cart(client):
    def add(book, quantity=1, override=False, using=None):
        data = {'quantity': quantity}
        if override:
            data['override'] = 'True'
        return (using or client).post(reverse('orders:cart_add', args=[book.pk]), data)
    return add


@pytest.fixture
def cart_session(client):
    def get(using=None):
        return (using or client).session.get('cart', {})
    return get


@pytest.fixture
def session_request(rf, db):
    """Запит із реальною сесією — для юніт-тестів Cart без проходження middleware."""
    request = rf.get('/')
    request.session = SessionStore()
    return request


@pytest.fixture
def order_data():
    return dict(ORDER_DATA)


@pytest.fixture
def stripe_checkout(mocker):
    return mocker.patch(
        'stripe.checkout.Session.create',
        return_value=mock.Mock(id='cs_test_123', url='https://checkout.stripe.com/c/pay/cs_test_123'),
    )
