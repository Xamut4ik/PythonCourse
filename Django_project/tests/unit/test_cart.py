from decimal import Decimal

import pytest

from orders.cart import Cart

pytestmark = pytest.mark.unit


def test_add_new_book(session_request, book):
    cart = Cart(session_request)
    cart.add(book, quantity=2)
    assert cart.cart == {str(book.pk): {'quantity': 2, 'price': '250.50'}}
    assert session_request.session.modified


def test_add_accumulates_and_override_replaces(session_request, book):
    cart = Cart(session_request)
    cart.add(book, 2)
    cart.add(book, 1)
    assert cart.cart[str(book.pk)]['quantity'] == 3
    cart.add(book, 1, override_quantity=True)
    assert cart.cart[str(book.pk)]['quantity'] == 1


def test_cart_persists_in_session(session_request, book):
    Cart(session_request).add(book, 2)
    assert len(Cart(session_request)) == 2


def test_remove(session_request, book, book2):
    cart = Cart(session_request)
    cart.add(book)
    cart.add(book2)
    cart.remove(book)
    cart.remove(book)
    assert list(cart.cart) == [str(book2.pk)]


def test_clear(session_request, book):
    cart = Cart(session_request)
    cart.add(book, 3)
    cart.clear()
    assert len(cart) == 0
    assert session_request.session['cart'] == {}


def test_len_and_total_price(session_request, book, book2):
    cart = Cart(session_request)
    cart.add(book, 2)
    cart.add(book2, 1)
    assert len(cart) == 3
    assert cart.get_total_price() == Decimal('681.00')


def test_empty_cart_total_is_zero(session_request):
    assert Cart(session_request).get_total_price() == Decimal('0')


def test_iter_yields_books_with_totals(session_request, book):
    cart = Cart(session_request)
    cart.add(book, 2)
    [item] = list(cart)
    assert item['book'] == book
    assert item['price'] == Decimal('250.50')
    assert item['total_price'] == Decimal('501.00')
    assert cart.cart[str(book.pk)] == {'quantity': 2, 'price': '250.50'}


def test_iter_skips_deleted_books(session_request, book, book2):
    cart = Cart(session_request)
    cart.add(book)
    cart.add(book2)
    book2.delete()
    assert [item['book'] for item in cart] == [book]
