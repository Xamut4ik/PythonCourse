from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from orders.models import Order
from tests.conftest import ORDER_DATA
from tests.factories import BookFactory, OrderFactory, OrderItemFactory

pytestmark = [pytest.mark.api, pytest.mark.django_db]


def order_payload(*items):
    return {**ORDER_DATA, 'items': [{'book_id': book.pk, 'quantity': quantity} for book, quantity in items]}


def test_create_order_with_nested_items(user_api, user, book, book2, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = user_api.post('/api/orders/', order_payload((book, 2), (book2, 1)), format='json')
    assert response.status_code == 201
    assert response.data['user'] == user.pk
    assert response.data['status'] == Order.Status.PENDING
    assert response.data['total_cost'] == '681.00'
    first = response.data['items'][0]
    assert first['book'] == {'id': book.pk, 'title': 'Кобзар', 'author': 'Шевченко', 'price': '250.50'}
    assert first['quantity'] == 2 and first['cost'] == '501.00'
    book.refresh_from_db()
    assert book.stock == 3
    assert len(mail.outbox) == 1


def test_create_order_with_insufficient_stock(user_api, book2):
    response = user_api.post('/api/orders/', order_payload((book2, 5)), format='json')
    assert response.status_code == 400
    assert 'items' in response.data
    book2.refresh_from_db()
    assert book2.stock == 1
    assert not Order.objects.exists()


@pytest.mark.parametrize('items', [[], [{'book_id': 1, 'quantity': 0}], [{'book_id': 999, 'quantity': 1}]])
def test_create_order_item_validation(user_api, items):
    response = user_api.post('/api/orders/', {**ORDER_DATA, 'items': items}, format='json')
    assert response.status_code == 400
    assert 'items' in response.data


def test_create_order_rejects_duplicate_books(user_api, book):
    response = user_api.post('/api/orders/', order_payload((book, 1), (book, 1)), format='json')
    assert response.status_code == 400


def test_create_order_validates_contact_data(user_api, book):
    response = user_api.post('/api/orders/', {**order_payload((book, 1)), 'email': 'bad'}, format='json')
    assert response.status_code == 400
    assert 'email' in response.data


def test_new_order_cannot_be_created_as_paid(user_api, book):
    response = user_api.post('/api/orders/', {**order_payload((book, 1)), 'status': 'paid'}, format='json')
    assert response.status_code == 400
    assert 'status' in response.data


def test_user_sees_only_own_orders_admin_sees_all(user_api, admin_api, user, other_user):
    own = OrderFactory(user=user)
    OrderFactory(user=other_user)
    response = user_api.get('/api/orders/')
    assert [item['id'] for item in response.data['results']] == [own.pk]
    assert admin_api.get('/api/orders/').data['count'] == 2


def test_foreign_order_is_not_found(user_api, other_user):
    foreign = OrderFactory(user=other_user)
    assert user_api.get(f'/api/orders/{foreign.pk}/').status_code == 404
    assert user_api.patch(f'/api/orders/{foreign.pk}/', {'city': 'Львів'}, format='json').status_code == 404
    assert user_api.delete(f'/api/orders/{foreign.pk}/').status_code == 404


def test_order_list_queries_do_not_grow(user_api, user, django_assert_max_num_queries):
    for _ in range(5):
        OrderItemFactory.create_batch(2, order=OrderFactory(user=user))
    with django_assert_max_num_queries(5):
        response = user_api.get('/api/orders/')
    assert response.data['count'] == 5


def test_owner_updates_contact_data_but_not_status(user_api, user):
    order = OrderFactory(user=user)
    assert user_api.patch(f'/api/orders/{order.pk}/', {'city': 'Львів'}, format='json').data['city'] == 'Львів'
    response = user_api.patch(f'/api/orders/{order.pk}/', {'status': 'paid'}, format='json')
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_owner_cannot_change_paid_order(user_api, user):
    order = OrderFactory(user=user, status=Order.Status.PAID)
    assert user_api.patch(f'/api/orders/{order.pk}/', {'city': 'Львів'}, format='json').status_code == 400


def test_order_items_are_read_only_on_update(user_api, user, book):
    item = OrderItemFactory(order=OrderFactory(user=user), quantity=1)
    response = user_api.patch(
        f'/api/orders/{item.order.pk}/', {'items': [{'book_id': book.pk, 'quantity': 5}]}, format='json',
    )
    assert response.status_code == 200
    assert [i['quantity'] for i in response.data['items']] == [1]


def test_admin_cancels_order_and_stock_is_restored(admin_api, user):
    book = BookFactory(stock=1)
    order = OrderFactory(user=user)
    OrderItemFactory(order=order, book=book, quantity=2)
    response = admin_api.patch(f'/api/orders/{order.pk}/', {'status': 'cancelled'}, format='json')
    assert response.status_code == 200
    book.refresh_from_db()
    assert book.stock == 3


def test_owner_deletes_pending_order_and_stock_is_restored(user_api, user):
    book = BookFactory(stock=0)
    order = OrderFactory(user=user)
    OrderItemFactory(order=order, book=book, quantity=2)
    assert user_api.delete(f'/api/orders/{order.pk}/').status_code == 204
    book.refresh_from_db()
    assert book.stock == 2


def test_owner_cannot_delete_paid_order_admin_can(user_api, admin_api, user):
    order = OrderFactory(user=user, status=Order.Status.PAID)
    assert user_api.delete(f'/api/orders/{order.pk}/').status_code == 403
    assert admin_api.delete(f'/api/orders/{order.pk}/').status_code == 204


def test_order_filters_and_search(user_api, user):
    paid = OrderFactory(user=user, status=Order.Status.PAID, city='Львів')
    old = OrderFactory(user=user)
    Order.objects.filter(pk=old.pk).update(created=timezone.now() - timedelta(days=10))
    today = timezone.localdate().isoformat()

    def found(params):
        return {item['id'] for item in user_api.get('/api/orders/', params).data['results']}

    assert found({'status': 'paid'}) == {paid.pk}
    assert found({'created_after': today}) == {paid.pk}
    assert found({'created_before': (timezone.localdate() - timedelta(days=5)).isoformat()}) == {old.pk}
    assert found({'search': 'Львів'}) == {paid.pk}


def test_order_total_uses_snapshot_price(user_api, user):
    book = BookFactory(price=Decimal('10.00'))
    order = OrderFactory(user=user)
    OrderItemFactory(order=order, book=book, quantity=3)
    book.price = Decimal('99.00')
    book.save()
    assert user_api.get(f'/api/orders/{order.pk}/').data['total_cost'] == '30.00'


def test_owner_cannot_delete_order_with_started_payment(user_api, user):
    order = OrderFactory(user=user, stripe_session_id='cs_test_123')
    assert user_api.delete(f'/api/orders/{order.pk}/').status_code == 403
    assert Order.objects.filter(pk=order.pk).exists()


def test_cancelled_order_cannot_be_reopened(admin_api, user):
    book = BookFactory(stock=1)
    order = OrderFactory(user=user)
    OrderItemFactory(order=order, book=book, quantity=2)
    admin_api.patch(f'/api/orders/{order.pk}/', {'status': 'cancelled'}, format='json')
    response = admin_api.patch(f'/api/orders/{order.pk}/', {'status': 'pending'}, format='json')
    assert response.status_code == 400
    assert admin_api.delete(f'/api/orders/{order.pk}/').status_code == 204
    book.refresh_from_db()
    assert book.stock == 3
