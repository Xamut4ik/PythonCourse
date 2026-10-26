from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from books.models import Book
from books.signals import DEFAULT_GROUP_NAME
from orders.models import Order
from tests.factories import PASSWORD, OrderFactory, OrderItemFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_registered_user_joins_default_group_and_can_log_in(client):
    response = client.post(reverse('books:register'), {
        'username': 'ivan', 'email': 'ivan@example.com',
        'password1': 'Sup3r-secret!', 'password2': 'Sup3r-secret!',
    }, follow=True)
    assert 'Реєстрація успішна' in response.content.decode()

    user = get_user_model().objects.get(username='ivan')
    assert user.groups.filter(name=DEFAULT_GROUP_NAME).exists()

    response = client.post(reverse('books:login'), {'username': 'ivan', 'password': 'Sup3r-secret!'}, follow=True)
    assert response.context['user'] == user
    assert 'Ви увійшли як ivan' in response.content.decode()


def test_login_with_wrong_password_fails(client, user):
    response = client.post(reverse('books:login'), {'username': user.username, 'password': 'wrong'})
    assert response.status_code == 200
    assert not response.context['user'].is_authenticated


def test_logout(client, user):
    client.login(username=user.username, password=PASSWORD)
    response = client.post(reverse('books:logout'), follow=True)
    assert response.redirect_chain == [(reverse('books:list'), 302)]
    assert not response.context['user'].is_authenticated
    assert 'Увійти' in response.content.decode()


@pytest.mark.parametrize('url_name, method', [
    ('books:create', 'get'),
    ('books:update', 'get'),
    ('books:delete', 'post'),
])
def test_anonymous_is_sent_to_login(client, book, url_name, method):
    args = [] if url_name == 'books:create' else [book.pk]
    url = reverse(url_name, args=args)
    response = getattr(client, method)(url)
    assert response.status_code == 302
    assert response.url == f"{reverse('books:login')}?next={url}"
    assert Book.objects.filter(pk=book.pk).exists()


def test_user_without_permissions_gets_403(auth_client, book):
    assert auth_client.get(reverse('books:create')).status_code == 403
    assert auth_client.post(reverse('books:update', args=[book.pk]), {'title': 'Hacked'}).status_code == 403
    assert auth_client.post(reverse('books:delete', args=[book.pk])).status_code == 403
    book.refresh_from_db()
    assert book.title == 'Кобзар'


def test_manager_group_can_create_update_and_delete_book(manager_client, category):
    response = manager_client.get(reverse('books:list'))
    assert reverse('books:create') in response.content.decode()

    response = manager_client.post(reverse('books:create'), {
        'title': 'Енеїда', 'author': 'Котляревський', 'category': category.pk,
        'price': '199.99', 'stock': 3, 'description': 'Поема',
    }, follow=True)
    assert [str(m) for m in response.context['messages']] == ['Книгу "Енеїда" створено.']
    book = Book.objects.get(title='Енеїда')

    manager_client.post(reverse('books:update', args=[book.pk]), {
        'title': 'Енеїда', 'author': 'Котляревський', 'category': category.pk,
        'price': '149.00', 'stock': 3, 'description': 'Поема',
    })
    book.refresh_from_db()
    assert book.price == Decimal('149.00')

    response = manager_client.get(reverse('books:delete', args=[book.pk]))
    assert 'books/book_delete.html' in [t.name for t in response.templates]
    manager_client.post(reverse('books:delete', args=[book.pk]))
    assert not Book.objects.filter(pk=book.pk).exists()


def test_foreign_order_is_hidden(client, book):
    owner = UserFactory()
    order = OrderFactory(user=owner)
    OrderItemFactory(order=order, book=book)
    client.force_login(UserFactory())

    for name in ('orders:pay', 'orders:payment_cancel', 'orders:order_status'):
        assert client.get(reverse(name, args=[order.pk])).status_code == 404

    client.force_login(owner)
    assert client.get(reverse('orders:payment_cancel', args=[order.pk])).status_code == 200


def test_guest_loses_access_to_order_with_new_session(client, book, order_data, stripe_checkout, add_to_cart):
    add_to_cart(book)
    client.post(reverse('orders:order_create'), order_data)
    order = Order.objects.get()
    assert client.get(reverse('orders:payment_cancel', args=[order.pk])).status_code == 200

    client.cookies.clear()
    assert client.get(reverse('orders:payment_cancel', args=[order.pk])).status_code == 404


def test_admin_requires_staff_and_shows_order_inline(client, user, book):
    order = OrderFactory()
    OrderItemFactory(order=order, book=book, quantity=2)
    change_url = reverse('admin:orders_order_change', args=[order.pk])

    client.force_login(user)
    assert client.get(change_url).url.startswith(reverse('admin:login'))

    admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', PASSWORD)
    client.force_login(admin)
    response = client.get(change_url)
    assert response.status_code == 200
    assert 'items-TOTAL_FORMS' in response.content.decode()
    assert '501.00' in response.content.decode()
    assert client.get(reverse('admin:orders_order_changelist')).status_code == 200
