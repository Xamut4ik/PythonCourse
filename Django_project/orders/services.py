import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from kombu.exceptions import OperationalError

from books.models import Book
from .emails import deliver_order_created_email
from .models import Order, OrderItem
from .tasks import send_order_confirmation_email

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def create_order_from_cart(cart, form, user=None):
    cart_items = list(cart)
    if not cart_items:
        raise OrderError(_('Your cart is empty.'))

    with transaction.atomic():
        order = form.save(commit=False)
        if user is not None and user.is_authenticated:
            order.user = user
        order.save()
        _add_order_items(order, [(item['book'].id, item['quantity']) for item in cart_items])
        transaction.on_commit(lambda: queue_order_created_email(order.id))

    return order


def create_order(user, contact_data, items):
    if not items:
        raise OrderError(_('Your cart is empty.'))

    with transaction.atomic():
        order = Order.objects.create(user=user, **contact_data)
        _add_order_items(order, items)
        transaction.on_commit(lambda: queue_order_created_email(order.id))

    return order


def _add_order_items(order, items):
    books = Book.objects.select_for_update().in_bulk([book_id for book_id, _quantity in items])
    order_items = []
    for book_id, quantity in items:
        book = books.get(book_id)
        if book is None:
            raise OrderError(_('Book #%(id)s does not exist.') % {'id': book_id})
        if book.stock < quantity:
            raise OrderError(
                _('Not enough copies of "%(title)s" in stock (available: %(stock)s).')
                % {'title': book.title, 'stock': book.stock}
            )
        book.stock -= quantity
        book.save(update_fields=['stock'])
        order_items.append(OrderItem(order=order, book=book, price=book.price, quantity=quantity))
    OrderItem.objects.bulk_create(order_items)


def restore_order_stock(order):
    with transaction.atomic():
        items = list(order.items.all())
        books = Book.objects.select_for_update().in_bulk([item.book_id for item in items])
        for item in items:
            book = books[item.book_id]
            book.stock += item.quantity
            book.save(update_fields=['stock'])


def send_order_created_email(order_id):
    try:
        deliver_order_created_email(order_id)
    except Exception:
        logger.exception('Не вдалося надіслати email для замовлення #%s', order_id)


def queue_order_created_email(order_id):
    language = translation.get_language()
    try:
        send_order_confirmation_email.delay(order_id, language)
    except OperationalError:
        logger.exception('Celery недоступний, email для замовлення #%s надсилається синхронно', order_id)
        with translation.override(language):
            send_order_created_email(order_id)


def create_checkout_session(order, request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    line_items = [
        {
            'price_data': {
                'currency': settings.STRIPE_CURRENCY,
                'unit_amount': int(item.price * 100),
                'product_data': {'name': item.book.title},
            },
            'quantity': item.quantity,
        }
        for item in order.items.select_related('book')
    ]
    success_url = request.build_absolute_uri(reverse('orders:payment_success'))
    session = stripe.checkout.Session.create(
        mode='payment',
        line_items=line_items,
        customer_email=order.email,
        client_reference_id=str(order.id),
        metadata={'order_id': str(order.id)},
        success_url=f'{success_url}?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=request.build_absolute_uri(reverse('orders:payment_cancel', args=[order.id])),
    )
    order.stripe_session_id = session.id
    order.save(update_fields=['stripe_session_id', 'updated'])
    return session


def mark_order_paid(session):
    if hasattr(session, 'to_dict'):
        session = session.to_dict()
    if session.get('payment_status') != 'paid':
        return None
    order_id = session.get('client_reference_id') or session.get('metadata', {}).get('order_id')
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            logger.warning('Stripe session %s посилається на неіснуюче замовлення %s', session.get('id'), order_id)
            return None
        if order.status == Order.Status.CANCELLED:
            payment_intent = session.get('payment_intent') or ''
            if payment_intent != order.stripe_payment_intent or not payment_intent:
                order.stripe_session_id = session.get('id') or order.stripe_session_id
                order.stripe_payment_intent = payment_intent or order.stripe_payment_intent
                order.save(update_fields=['stripe_session_id', 'stripe_payment_intent', 'updated'])
                logger.error(
                    'Оплачено скасоване замовлення #%s (payment intent %s), потрібне повернення коштів',
                    order.id, payment_intent or '-',
                )
        elif not order.is_paid:
            order.status = Order.Status.PAID
            order.stripe_session_id = session.get('id') or order.stripe_session_id
            order.stripe_payment_intent = session.get('payment_intent') or ''
            order.save(update_fields=['status', 'stripe_session_id', 'stripe_payment_intent', 'updated'])
            logger.info('Замовлення #%s оплачено', order.id)
    return order
