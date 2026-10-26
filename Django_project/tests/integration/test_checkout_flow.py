import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
import stripe
from django.core import mail
from django.urls import reverse

from books.models import Book
from orders.models import Order, OrderItem

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

STRIPE_URL = 'https://checkout.stripe.com/c/pay/cs_test_123'


def paid_session(order):
    return stripe.checkout.Session.construct_from({
        'id': 'cs_test_123', 'payment_status': 'paid',
        'client_reference_id': str(order.pk), 'payment_intent': 'pi_123',
    }, 'sk_test_dummy')


def test_register_login_buy_pay_and_get_email(
    client, book, book2, order_data, stripe_checkout, mocker, django_capture_on_commit_callbacks,
):
    response = client.post(reverse('books:register'), {
        'username': 'olena', 'email': 'olena@example.com',
        'password1': 'Sup3r-secret!', 'password2': 'Sup3r-secret!',
    })
    assert response.url == reverse('books:login')
    response = client.post(reverse('books:login'), {'username': 'olena', 'password': 'Sup3r-secret!'})
    assert response.url == reverse('books:list')

    client.post(reverse('orders:cart_add', args=[book.pk]), {'quantity': 2})
    client.post(reverse('orders:cart_add', args=[book2.pk]), {'quantity': 1})
    response = client.get(reverse('orders:cart_detail'))
    assert response.context['cart'].get_total_price() == Decimal('681.00')

    order_data['email'] = 'olena@example.com'
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse('orders:order_create'), order_data)
    order = Order.objects.get()
    assert response.url == reverse('orders:pay', args=[order.pk])
    response = client.get(response.url)
    assert response.url == STRIPE_URL

    order.refresh_from_db()
    assert order.user.username == 'olena'
    assert order.stripe_session_id == 'cs_test_123'
    assert stripe_checkout.call_args.kwargs['line_items'] == [
        {'price_data': {'currency': 'uah', 'unit_amount': 25050, 'product_data': {'name': 'Кобзар'}}, 'quantity': 2},
        {'price_data': {'currency': 'uah', 'unit_amount': 18000,
                        'product_data': {'name': 'Тіні забутих предків'}}, 'quantity': 1},
    ]
    assert stripe_checkout.call_args.kwargs['success_url'].startswith('http://testserver/uk/payment/success/')
    assert client.session['cart'] == {}
    assert list(Book.objects.order_by('pk').values_list('stock', flat=True)) == [3, 0]

    [email] = mail.outbox
    assert email.to == ['olena@example.com']
    assert email.subject == f'Замовлення #{order.pk} створено'
    assert 'Кобзар × 2 — 501,00 грн' in email.body
    assert 'Разом: 681,00 грн' in email.body

    mocker.patch('stripe.checkout.Session.retrieve', return_value=paid_session(order))
    response = client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_123'})
    assert 'Оплачено' in response.content.decode()
    order.refresh_from_db()
    assert order.is_paid and order.stripe_payment_intent == 'pi_123'

    assert client.get(reverse('orders:order_status', args=[order.pk])).json()['is_paid'] is True


def test_guest_checkout_paid_via_signed_webhook(client, book, order_data, stripe_checkout, add_to_cart):
    add_to_cart(book, 1)
    client.post(reverse('orders:order_create'), order_data)
    order = Order.objects.get()
    assert order.user is None

    payload = json.dumps({
        'id': 'evt_1', 'object': 'event', 'type': 'checkout.session.completed',
        'data': {'object': {
            'id': 'cs_test_123', 'object': 'checkout.session', 'payment_status': 'paid',
            'client_reference_id': str(order.pk), 'payment_intent': 'pi_999',
        }},
    })
    timestamp = int(time.time())
    signature = hmac.new(b'whsec_dummy', f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()

    response = client.post(
        reverse('stripe_webhook'), payload, content_type='application/json',
        HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature}',
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert order.stripe_payment_intent == 'pi_999'


def test_webhook_rejects_bad_signature(client, book, order_data, stripe_checkout, add_to_cart):
    add_to_cart(book)
    client.post(reverse('orders:order_create'), order_data)
    response = client.post(
        reverse('stripe_webhook'), b'{"type": "checkout.session.completed"}',
        content_type='application/json', HTTP_STRIPE_SIGNATURE='t=1,v1=forged',
    )
    assert response.status_code == 400
    assert Order.objects.get().status == Order.Status.PENDING


def test_out_of_stock_rolls_back_whole_order(
    client, book, book2, order_data, add_to_cart, cart_session, django_capture_on_commit_callbacks,
):
    add_to_cart(book, 2)
    add_to_cart(book2, 1)
    Book.objects.filter(pk=book2.pk).update(stock=0)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse('orders:order_create'), order_data, follow=True)

    assert response.redirect_chain == [(reverse('orders:cart_detail'), 302)]
    assert 'Недостатньо примірників' in response.content.decode()
    assert not Order.objects.exists() and not OrderItem.objects.exists()
    book.refresh_from_db()
    assert book.stock == 5
    assert mail.outbox == []
    assert cart_session() != {}


def test_stripe_outage_then_successful_retry(client, book, order_data, mocker, add_to_cart):
    create = mocker.patch('stripe.checkout.Session.create', side_effect=stripe.APIConnectionError('down'))
    add_to_cart(book)

    response = client.post(reverse('orders:order_create'), order_data, follow=True)
    order = Order.objects.get()
    assert response.redirect_chain[-1] == (reverse('orders:payment_cancel', args=[order.pk]), 302)
    assert 'Не вдалося перейти до оплати' in response.content.decode()
    assert reverse('orders:pay', args=[order.pk]) in response.content.decode()

    create.side_effect = None
    create.return_value = mocker.Mock(id='cs_retry', url=STRIPE_URL)
    response = client.get(reverse('orders:pay', args=[order.pk]))
    assert response.url == STRIPE_URL


def test_cart_update_remove_and_clear(client, book, book2, add_to_cart, cart_session):
    add_to_cart(book, 2)
    add_to_cart(book, 3, override=True)
    add_to_cart(book2)
    assert cart_session()[str(book.pk)]['quantity'] == 3

    client.post(reverse('orders:cart_remove', args=[book.pk]))
    assert list(cart_session()) == [str(book2.pk)]

    response = client.post(reverse('orders:cart_clear'), follow=True)
    assert cart_session() == {}
    assert 'Кошик порожній.' in response.content.decode()


def test_email_is_sent_in_active_language(client, book, order_data, stripe_checkout, django_capture_on_commit_callbacks):
    client.post('/en/cart/add/%d/' % book.pk, {'quantity': 1})
    with django_capture_on_commit_callbacks(execute=True):
        client.post('/en/orders/create/', order_data)

    [email] = mail.outbox
    assert email.subject == f'Order #{Order.objects.get().pk} created'
    assert 'Hello, Тарас!' in email.body
    assert '250.50 UAH' in email.body
