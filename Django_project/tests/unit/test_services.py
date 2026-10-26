from smtplib import SMTPException

import pytest
from django.core import mail

from orders.cart import Cart
from orders.forms import OrderCreateForm
from orders.models import Order
from orders.services import OrderError, create_order_from_cart, mark_order_paid, send_order_created_email
from tests.factories import OrderFactory, OrderItemFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_order_from_empty_cart_raises(session_request, order_data):
    form = OrderCreateForm(order_data)
    assert form.is_valid()
    with pytest.raises(OrderError, match='Кошик порожній.'):
        create_order_from_cart(Cart(session_request), form)
    assert not Order.objects.exists()


def test_email_failure_is_logged_not_raised(mocker, caplog):
    order = OrderItemFactory().order
    mocker.patch('orders.services.send_mail', side_effect=SMTPException('smtp down'))

    send_order_created_email(order.pk)

    assert mail.outbox == []
    assert f'#{order.pk}' in caplog.text


def test_mark_order_paid_ignores_unpaid_session():
    order = OrderFactory()
    assert mark_order_paid({'payment_status': 'unpaid', 'client_reference_id': str(order.pk)}) is None
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_mark_order_paid_with_unknown_order(caplog):
    assert mark_order_paid({'id': 'cs_1', 'payment_status': 'paid', 'metadata': {'order_id': '999'}}) is None
    assert 'cs_1' in caplog.text


def test_mark_order_paid_is_idempotent():
    order = OrderFactory()
    session = {'id': 'cs_1', 'payment_status': 'paid', 'client_reference_id': str(order.pk), 'payment_intent': 'pi_1'}
    mark_order_paid(session)
    session['payment_intent'] = 'pi_other'
    assert mark_order_paid(session).stripe_payment_intent == 'pi_1'
