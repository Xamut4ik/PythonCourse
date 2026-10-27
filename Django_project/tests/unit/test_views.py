import pytest
import stripe
from django.http import HttpResponse
from django.urls import reverse

from books.middleware import RequestLogMiddleware
from orders.models import Order
from tests.factories import BookFactory, OrderFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_home_redirects_to_book_list(client):
    response = client.get(reverse('home'))
    assert response.status_code == 302
    assert response.url == reverse('books:list')


def test_book_list_template_and_context(client, book):
    response = client.get(reverse('books:list'))
    assert response.status_code == 200
    assert 'books/book_list.html' in [t.name for t in response.templates]
    assert list(response.context['books']) == [book]


def test_book_list_search_and_pagination(client, category):
    BookFactory.create_batch(7, category=category, author='Леся Українка')
    target = BookFactory(title='Кобзар', author='Шевченко', category=category)

    response = client.get(reverse('books:list'), {'q': 'Кобз'})
    assert list(response.context['books']) == [target]
    assert response.context['query'] == 'Кобз'

    response = client.get(reverse('books:list'))
    assert response.context['is_paginated']
    assert len(response.context['books']) == 6


def test_book_detail(client, book):
    response = client.get(reverse('books:detail', args=[book.pk]))
    assert response.status_code == 200
    assert response.context['book'] == book
    assert reverse('orders:cart_add', args=[book.pk]) in response.content.decode()


def test_book_detail_404(client):
    assert client.get(reverse('books:detail', args=[999])).status_code == 404


def test_create_book_requires_login(client):
    response = client.get(reverse('books:create'))
    assert response.status_code == 302
    assert response.url.startswith(reverse('books:login'))


def test_create_book_requires_permission(auth_client):
    assert auth_client.get(reverse('books:create')).status_code == 403


def test_create_book_page_for_manager(manager_client):
    response = manager_client.get(reverse('books:create'))
    assert response.status_code == 200
    assert 'books/book_create.html' in [t.name for t in response.templates]


def test_cart_detail_context(client, book, add_to_cart):
    add_to_cart(book, 2)
    response = client.get(reverse('orders:cart_detail'))
    [item] = response.context['items']
    assert item['book'] == book
    assert item['update_form'].initial == {'quantity': 2, 'override': True}


def test_cart_add_invalid_quantity(client, book, add_to_cart, cart_session):
    response = add_to_cart(book, 0)
    assert response.status_code == 302
    assert cart_session() == {}
    messages = [str(m) for m in response.wsgi_request._messages]
    assert messages == ['Некоректна кількість.']


def test_cart_add_more_than_stock(client, book2, add_to_cart, cart_session):
    add_to_cart(book2, 2)
    assert cart_session() == {}


def test_cart_add_unknown_book_404(client):
    assert client.post(reverse('orders:cart_add', args=[999]), {'quantity': 1}).status_code == 404


def test_order_create_with_empty_cart_redirects(client):
    response = client.get(reverse('orders:order_create'))
    assert response.status_code == 302
    assert response.url == reverse('orders:cart_detail')


def test_order_create_prefills_user_data(auth_client, user, book, add_to_cart):
    add_to_cart(book, using=auth_client)
    response = auth_client.get(reverse('orders:order_create'))
    assert response.status_code == 200
    assert response.context['form'].initial == {
        'first_name': user.first_name, 'last_name': user.last_name, 'email': user.email,
    }


def test_pay_for_paid_order_redirects_to_catalog(auth_client, user):
    order = OrderFactory(user=user, status=Order.Status.PAID)
    response = auth_client.get(reverse('orders:pay', args=[order.pk]))
    assert response.url == reverse('books:list')


def test_payment_success_without_session_id_404(client):
    assert client.get(reverse('orders:payment_success')).status_code == 404


def test_payment_success_with_unknown_session_404(client, mocker):
    mocker.patch('stripe.checkout.Session.retrieve', side_effect=stripe.InvalidRequestError('No such session', None))
    assert client.get(reverse('orders:payment_success'), {'session_id': 'cs_bad'}).status_code == 404


def test_webhook_ignores_unrelated_events(client, mocker):
    mocker.patch('stripe.Webhook.construct_event', return_value={'type': 'payment_intent.created', 'data': {}})
    mark_paid = mocker.patch('orders.views.mark_order_paid')
    response = client.post(reverse('stripe_webhook'), b'{}', content_type='application/json')
    assert response.status_code == 200
    mark_paid.assert_not_called()


def test_webhook_url_has_no_language_prefix():
    assert reverse('stripe_webhook') == '/payment/webhook/'


def test_request_log_middleware_prints_request(rf, capsys):
    middleware = RequestLogMiddleware(lambda request: HttpResponse(status=201))
    response = middleware(rf.post('/uk/books/'))
    assert response.status_code == 201
    assert capsys.readouterr().out.strip() == 'POST /uk/books/ 201'


def paid_stripe_session(order):
    return stripe.checkout.Session.construct_from({
        'id': 'cs_test_1', 'payment_status': 'paid',
        'client_reference_id': str(order.pk), 'payment_intent': 'pi_1',
    }, 'sk_test_dummy')


def test_payment_success_for_cancelled_order_shows_refund_notice(auth_client, user, mocker):
    order = OrderFactory(user=user, status=Order.Status.CANCELLED, email='taras@example.com')
    mocker.patch('stripe.checkout.Session.retrieve', return_value=paid_stripe_session(order))
    response = auth_client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_1'})
    content = response.content.decode()
    assert response.status_code == 200
    assert 'Це замовлення скасовано' in content
    assert 'кошти буде повернуто' in content
    assert 'taras@example.com' in content
    assert 'Дякуємо за покупку!' not in content
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_payment_success_for_paid_order_shows_thanks(auth_client, user, mocker):
    order = OrderFactory(user=user)
    mocker.patch('stripe.checkout.Session.retrieve', return_value=paid_stripe_session(order))
    content = auth_client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_1'}).content.decode()
    assert 'Дякуємо за покупку!' in content
    assert 'скасовано' not in content


def test_payment_success_cancelled_page_in_english(auth_client, user, mocker):
    order = OrderFactory(user=user, status=Order.Status.CANCELLED)
    mocker.patch('stripe.checkout.Session.retrieve', return_value=paid_stripe_session(order))
    response = auth_client.get('/en/payment/success/', {'session_id': 'cs_test_1'})
    assert 'This order has been cancelled' in response.content.decode()


def test_cancelled_order_with_unpaid_session_has_no_refund_notice(auth_client, user, mocker):
    order = OrderFactory(user=user, status=Order.Status.CANCELLED)
    session = stripe.checkout.Session.construct_from({
        'id': 'cs_test_1', 'payment_status': 'unpaid', 'client_reference_id': str(order.pk),
    }, 'sk_test_dummy')
    mocker.patch('stripe.checkout.Session.retrieve', return_value=session)
    content = auth_client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_1'}).content.decode()
    assert 'Це замовлення скасовано' in content
    assert 'кошти буде повернуто' not in content
