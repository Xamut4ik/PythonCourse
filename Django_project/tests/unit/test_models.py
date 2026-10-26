from decimal import Decimal

import pytest
from django.utils import translation

from books.signals import DEFAULT_GROUP_NAME
from orders.models import Order
from tests.factories import BookFactory, CategoryFactory, OrderFactory, OrderItemFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_category_str():
    assert str(CategoryFactory(name='Поезія')) == 'Поезія'


def test_book_str_and_in_stock():
    book = BookFactory(title='Кобзар', stock=2)
    assert str(book) == 'Кобзар'
    assert book.in_stock
    book.stock = 0
    assert not book.in_stock


def test_book_belongs_to_category():
    category = CategoryFactory()
    books = BookFactory.create_batch(3, category=category)
    assert set(category.book_set.all()) == set(books)


def test_order_str_is_translated():
    order = OrderFactory()
    with translation.override('uk'):
        assert str(order) == f'Замовлення #{order.pk}'
    with translation.override('en'):
        assert str(order) == f'Order #{order.pk}'


def test_verbose_names_are_translated():
    with translation.override('uk'):
        assert str(Order._meta.verbose_name) == 'замовлення'
        assert str(Order._meta.get_field('city').verbose_name) == 'місто'
    with translation.override('en'):
        assert str(Order._meta.get_field('city').verbose_name) == 'city'


def test_order_total_cost_sums_items():
    order = OrderFactory()
    OrderItemFactory(order=order, price=Decimal('100.00'), quantity=2)
    OrderItemFactory(order=order, price=Decimal('50.25'), quantity=1)
    assert order.get_total_cost() == Decimal('250.25')


def test_empty_order_total_is_zero():
    assert OrderFactory().get_total_cost() == Decimal('0')


def test_order_status_defaults_to_pending():
    order = OrderFactory()
    assert order.status == Order.Status.PENDING
    assert not order.is_paid
    order.status = Order.Status.PAID
    assert order.is_paid


def test_order_item_cost_and_str():
    item = OrderItemFactory(book=BookFactory(title='Кобзар'), price=Decimal('99.90'), quantity=3)
    assert item.get_cost() == Decimal('299.70')
    assert str(item) == 'Кобзар x 3'


def test_order_relations():
    user = UserFactory()
    order = OrderFactory(user=user)
    item = OrderItemFactory(order=order)
    assert list(user.orders.all()) == [order]
    assert list(order.items.all()) == [item]
    assert list(item.book.order_items.all()) == [item]


def test_new_user_is_added_to_default_group():
    user = UserFactory()
    assert list(user.groups.values_list('name', flat=True)) == [DEFAULT_GROUP_NAME]
