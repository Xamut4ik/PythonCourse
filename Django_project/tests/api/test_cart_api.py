import pytest

from orders.models import Cart, CartItem, Order
from tests.conftest import ORDER_DATA

pytestmark = [pytest.mark.api, pytest.mark.django_db]


def test_cart_requires_authentication(api_client):
    assert api_client.get('/api/cart/').status_code == 401
    assert api_client.post('/api/cart-items/', {}, format='json').status_code == 401


def test_create_cart_with_nested_items(user_api, user, book, book2):
    payload = {'items': [{'book_id': book.pk, 'quantity': 2}, {'book_id': book2.pk, 'quantity': 1}]}
    response = user_api.post('/api/cart/', payload, format='json')
    assert response.status_code == 201
    assert response.data['user'] == user.pk
    assert response.data['total_price'] == '681.00'
    assert [item['book']['title'] for item in response.data['items']] == ['Кобзар', 'Тіні забутих предків']


def test_user_can_have_only_one_cart(user_api, user):
    Cart.objects.create(user=user)
    assert user_api.post('/api/cart/', {}, format='json').status_code == 400


def test_cart_items_validate_quantity_and_stock(user_api, book2):
    zero = user_api.post('/api/cart/', {'items': [{'book_id': book2.pk, 'quantity': 0}]}, format='json')
    too_many = user_api.post('/api/cart/', {'items': [{'book_id': book2.pk, 'quantity': 2}]}, format='json')
    assert zero.status_code == 400
    assert too_many.status_code == 400
    assert not Cart.objects.exists()


def test_update_cart_replaces_items(user_api, user, book, book2):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, book=book, quantity=1)
    response = user_api.put(f'/api/cart/{cart.pk}/', {'items': [{'book_id': book2.pk, 'quantity': 1}]}, format='json')
    assert response.status_code == 200
    assert [item['book']['id'] for item in response.data['items']] == [book2.pk]
    assert list(cart.items.values_list('book_id', flat=True)) == [book2.pk]


def test_add_item_creates_cart_automatically(user_api, user, book):
    response = user_api.post('/api/cart-items/', {'book_id': book.pk, 'quantity': 3}, format='json')
    assert response.status_code == 201
    assert response.data['cost'] == '751.50'
    assert user.cart.items.get().quantity == 3


def test_add_same_book_twice_is_rejected(user_api, book):
    user_api.post('/api/cart-items/', {'book_id': book.pk, 'quantity': 1}, format='json')
    response = user_api.post('/api/cart-items/', {'book_id': book.pk, 'quantity': 1}, format='json')
    assert response.status_code == 400
    assert 'book_id' in response.data


def test_change_and_remove_cart_item(user_api, user, book):
    item = CartItem.objects.create(cart=Cart.objects.create(user=user), book=book, quantity=1)
    assert user_api.patch(f'/api/cart-items/{item.pk}/', {'quantity': 4}, format='json').data['quantity'] == 4
    assert user_api.patch(f'/api/cart-items/{item.pk}/', {'quantity': 6}, format='json').status_code == 400
    assert user_api.delete(f'/api/cart-items/{item.pk}/').status_code == 204
    assert not CartItem.objects.exists()


def test_foreign_cart_is_hidden_admin_sees_all(user_api, other_api, admin_api, user, other_user, book):
    own = Cart.objects.create(user=user)
    foreign = Cart.objects.create(user=other_user)
    foreign_item = CartItem.objects.create(cart=foreign, book=book, quantity=1)
    assert [c['id'] for c in user_api.get('/api/cart/').data['results']] == [own.pk]
    assert user_api.get(f'/api/cart/{foreign.pk}/').status_code == 404
    assert user_api.patch(f'/api/cart-items/{foreign_item.pk}/', {'quantity': 2}, format='json').status_code == 404
    assert admin_api.get('/api/cart/').data['count'] == 2
    assert admin_api.patch(f'/api/cart-items/{foreign_item.pk}/', {'quantity': 2}, format='json').status_code == 200


def test_checkout_creates_order_and_clears_cart(user_api, user, book):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, book=book, quantity=2)
    response = user_api.post(f'/api/cart/{cart.pk}/checkout/', ORDER_DATA, format='json')
    assert response.status_code == 201
    order = Order.objects.get()
    assert response.data['id'] == order.pk
    assert order.user == user
    assert response.data['total_cost'] == '501.00'
    assert not cart.items.exists()
    book.refresh_from_db()
    assert book.stock == 3


def test_checkout_empty_cart_fails(user_api, user):
    cart = Cart.objects.create(user=user)
    response = user_api.post(f'/api/cart/{cart.pk}/checkout/', ORDER_DATA, format='json')
    assert response.status_code == 400
    assert not Order.objects.exists()


def test_checkout_requires_contact_data(user_api, user, book):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, book=book, quantity=1)
    response = user_api.post(f'/api/cart/{cart.pk}/checkout/', {'first_name': 'Тарас'}, format='json')
    assert response.status_code == 400
    assert 'email' in response.data
    assert cart.items.exists()


def test_delete_cart(user_api, user):
    cart = Cart.objects.create(user=user)
    assert user_api.delete(f'/api/cart/{cart.pk}/').status_code == 204
    assert not Cart.objects.exists()


def test_cart_and_item_str(user, book):
    cart = Cart.objects.create(user=user)
    item = CartItem.objects.create(cart=cart, book=book, quantity=2)
    assert str(cart) == f'Cart of {user}'
    assert str(item) == 'Кобзар x 2'


def test_cart_item_quantity_defaults_to_one(user_api, book):
    response = user_api.post('/api/cart-items/', {'book_id': book.pk}, format='json')
    assert response.status_code == 201
    assert response.data['quantity'] == 1
