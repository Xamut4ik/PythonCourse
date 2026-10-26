import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

import stripe
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from books.models import Book, Category
from .models import Order, OrderItem

ORDER_DATA = {
    'first_name': 'Тарас',
    'last_name': 'Шевченко',
    'email': 'taras@example.com',
    'address': 'вул. Хрещатик, 1',
    'city': 'Київ',
}


@override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_WEBHOOK_SECRET='whsec_dummy')
class OrdersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Класика', slug='classic')
        cls.book1 = Book.objects.create(
            title='Кобзар', author='Шевченко', price=Decimal('250.50'),
            description='-', stock=5, category=category,
        )
        cls.book2 = Book.objects.create(
            title='Тіні забутих предків', author='Коцюбинський', price=Decimal('180.00'),
            description='-', stock=1, category=category,
        )

    def add_to_cart(self, book, quantity=1, override=False):
        data = {'quantity': quantity}
        if override:
            data['override'] = 'True'
        return self.client.post(reverse('orders:cart_add', args=[book.pk]), data)

    def cart(self):
        return self.client.session.get('cart', {})


class CartTests(OrdersTestCase):
    def test_add_accumulates_and_override_replaces(self):
        self.add_to_cart(self.book1, 2)
        self.add_to_cart(self.book1, 1)
        self.assertEqual(self.cart()[str(self.book1.pk)], {'quantity': 3, 'price': '250.50'})

        self.add_to_cart(self.book1, 1, override=True)
        self.assertEqual(self.cart()[str(self.book1.pk)]['quantity'], 1)

    def test_add_more_than_stock_is_rejected(self):
        self.add_to_cart(self.book2, 2)
        self.assertEqual(self.cart(), {})

    def test_remove_and_clear(self):
        self.add_to_cart(self.book1)
        self.add_to_cart(self.book2)
        self.client.post(reverse('orders:cart_remove', args=[self.book1.pk]))
        self.assertEqual(list(self.cart()), [str(self.book2.pk)])

        self.client.post(reverse('orders:cart_clear'))
        self.assertEqual(self.cart(), {})

    def test_cart_page_shows_total(self):
        self.add_to_cart(self.book1, 2)
        response = self.client.get(reverse('orders:cart_detail'))
        self.assertContains(response, 'Кобзар')
        self.assertContains(response, '501.00')


class OrderCreateTests(OrdersTestCase):
    def test_creates_order_items_decrements_stock_and_sends_email(self):
        self.add_to_cart(self.book1, 2)
        self.add_to_cart(self.book2, 1)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('orders:order_create'), ORDER_DATA)

        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:pay', args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.get_total_cost(), Decimal('681.00'))
        self.book1.refresh_from_db()
        self.book2.refresh_from_db()
        self.assertEqual((self.book1.stock, self.book2.stock), (3, 0))
        self.assertEqual(self.cart(), {})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['taras@example.com'])
        self.assertIn(f'#{order.pk}', mail.outbox[0].subject)
        self.assertIn('Кобзар × 2', mail.outbox[0].body)

    def test_out_of_stock_rolls_back_whole_order(self):
        self.add_to_cart(self.book1, 2)
        self.add_to_cart(self.book2, 1)
        # Хтось купив останній примірник, поки книга лежала в кошику
        Book.objects.filter(pk=self.book2.pk).update(stock=0)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('orders:order_create'), ORDER_DATA)

        self.assertRedirects(response, reverse('orders:cart_detail'))
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.book1.refresh_from_db()
        self.assertEqual(self.book1.stock, 5)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotEqual(self.cart(), {})

    def test_empty_cart_redirects(self):
        response = self.client.post(reverse('orders:order_create'), ORDER_DATA)
        self.assertRedirects(response, reverse('orders:cart_detail'))
        self.assertFalse(Order.objects.exists())

    def test_authenticated_user_is_attached(self):
        user = get_user_model().objects.create_user('taras', 'taras@example.com', 'pass12345')
        self.client.force_login(user)
        self.add_to_cart(self.book1)
        self.client.post(reverse('orders:order_create'), ORDER_DATA)
        self.assertEqual(Order.objects.get().user, user)


class StripeTests(OrdersTestCase):
    def create_order(self):
        self.add_to_cart(self.book1, 2)
        self.client.post(reverse('orders:order_create'), ORDER_DATA)
        return Order.objects.get()

    @mock.patch('stripe.checkout.Session.create')
    def test_pay_creates_checkout_session_and_redirects(self, create):
        create.return_value = mock.Mock(id='cs_test_123', url='https://checkout.stripe.com/c/pay/cs_test_123')
        order = self.create_order()

        response = self.client.get(reverse('orders:pay', args=[order.pk]))

        self.assertRedirects(response, 'https://checkout.stripe.com/c/pay/cs_test_123', fetch_redirect_response=False)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs['mode'], 'payment')
        self.assertEqual(kwargs['client_reference_id'], str(order.pk))
        self.assertEqual(kwargs['line_items'], [{
            'price_data': {'currency': 'uah', 'unit_amount': 25050, 'product_data': {'name': 'Кобзар'}},
            'quantity': 2,
        }])
        self.assertIn('session_id={CHECKOUT_SESSION_ID}', kwargs['success_url'])
        order.refresh_from_db()
        self.assertEqual(order.stripe_session_id, 'cs_test_123')

    @mock.patch('stripe.checkout.Session.create', side_effect=stripe.APIConnectionError('down'))
    def test_stripe_error_redirects_to_cancel_page(self, create):
        order = self.create_order()
        response = self.client.get(reverse('orders:pay', args=[order.pk]))
        self.assertRedirects(response, reverse('orders:payment_cancel', args=[order.pk]))

    def test_foreign_order_is_hidden(self):
        order = self.create_order()
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse('orders:pay', args=[order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('orders:payment_cancel', args=[order.pk])).status_code, 404)

    @mock.patch('stripe.checkout.Session.retrieve')
    def test_success_page_marks_order_paid(self, retrieve):
        order = self.create_order()
        retrieve.return_value = stripe.checkout.Session.construct_from({
            'id': 'cs_test_123', 'payment_status': 'paid',
            'client_reference_id': str(order.pk), 'payment_intent': 'pi_123',
        }, 'sk_test_dummy')

        response = self.client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_123'})

        self.assertContains(response, 'Оплачено')
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.stripe_payment_intent, 'pi_123')

    @mock.patch('stripe.Webhook.construct_event')
    def test_webhook_marks_order_paid(self, construct_event):
        order = self.create_order()
        construct_event.return_value = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'id': 'cs_test_123', 'payment_status': 'paid',
                'client_reference_id': str(order.pk), 'payment_intent': 'pi_123',
            }},
        }

        response = self.client.post(
            reverse('orders:stripe_webhook'), b'{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='t=1,v1=abc',
        )

        self.assertEqual(response.status_code, 200)
        construct_event.assert_called_once_with(b'{}', 't=1,v1=abc', 'whsec_dummy')
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_webhook_with_real_signature(self):
        order = self.create_order()
        payload = json.dumps({
            'id': 'evt_1', 'object': 'event', 'type': 'checkout.session.completed',
            'data': {'object': {
                'id': 'cs_test_123', 'object': 'checkout.session', 'payment_status': 'paid',
                'client_reference_id': str(order.pk), 'payment_intent': 'pi_123',
            }},
        })
        timestamp = int(time.time())
        signature = hmac.new(b'whsec_dummy', f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse('orders:stripe_webhook'), payload,
            content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature}',
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.stripe_payment_intent, 'pi_123')

    def test_webhook_rejects_bad_signature(self):
        response = self.client.post(
            reverse('orders:stripe_webhook'), b'{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='bad',
        )
        self.assertEqual(response.status_code, 400)


class AdminTests(OrdersTestCase):
    def test_order_change_page_has_item_inline(self):
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pass12345')
        self.client.force_login(admin)
        self.add_to_cart(self.book1, 2)
        self.client.post(reverse('orders:order_create'), ORDER_DATA)
        order = Order.objects.get()

        response = self.client.get(reverse('admin:orders_order_change', args=[order.pk]))

        self.assertContains(response, 'items-TOTAL_FORMS')
        self.assertContains(response, '501.00')
        self.assertEqual(self.client.get(reverse('admin:orders_order_changelist')).status_code, 200)
