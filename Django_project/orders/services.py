import logging

import stripe
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from books.models import Book
from .models import Order, OrderItem

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def create_order_from_cart(cart, form, user=None):
    """Створює замовлення з кошика. Усе або нічого: при будь-якій помилці зміни відкочуються."""
    cart_items = list(cart)
    if not cart_items:
        raise OrderError('Кошик порожній.')

    with transaction.atomic():
        order = form.save(commit=False)
        if user is not None and user.is_authenticated:
            order.user = user
        order.save()

        # Блокуємо рядки книг до кінця транзакції, щоб паралельні замовлення не продали більше, ніж є на складі
        books = Book.objects.select_for_update().in_bulk(
            [item['book'].id for item in cart_items]
        )
        order_items = []
        for item in cart_items:
            book = books[item['book'].id]
            quantity = item['quantity']
            if book.stock < quantity:
                raise OrderError(
                    f'Недостатньо примірників "{book.title}" на складі (доступно: {book.stock}).'
                )
            book.stock -= quantity
            book.save(update_fields=['stock'])
            order_items.append(OrderItem(order=order, book=book, price=book.price, quantity=quantity))
        OrderItem.objects.bulk_create(order_items)

        # Лист відправляємо лише після успішного коміту, а не для відкоченого замовлення
        transaction.on_commit(lambda: send_order_created_email(order.id))

    return order


def send_order_created_email(order_id):
    order = Order.objects.prefetch_related('items__book').get(pk=order_id)
    message = render_to_string('orders/emails/order_created.txt', {'order': order})
    try:
        send_mail(
            subject=f'Замовлення #{order.id} створено',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
        )
    except Exception:
        # Замовлення вже збережене, тому збій пошти не повинен ламати оформлення
        logger.exception('Не вдалося надіслати email для замовлення #%s', order.id)
    else:
        logger.info('Email про замовлення #%s надіслано на %s', order.id, order.email)


def create_checkout_session(order, request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    line_items = [
        {
            'price_data': {
                'currency': settings.STRIPE_CURRENCY,
                # Stripe приймає суму в мінімальних одиницях валюти (копійках)
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
    """Позначає замовлення оплаченим за даними Stripe Checkout Session. Повторний виклик безпечний."""
    if hasattr(session, 'to_dict'):
        # StripeObject у нових версіях stripe не є dict і не має .get()
        session = session.to_dict()
    if session.get('payment_status') != 'paid':
        return None
    order_id = session.get('client_reference_id') or session.get('metadata', {}).get('order_id')
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            logger.warning('Stripe session %s посилається на неіснуюче замовлення %s', session.get('id'), order_id)
            return None
        if not order.is_paid:
            order.status = Order.Status.PAID
            order.stripe_session_id = session.get('id') or order.stripe_session_id
            order.stripe_payment_intent = session.get('payment_intent') or ''
            order.save(update_fields=['status', 'stripe_session_id', 'stripe_payment_intent', 'updated'])
            logger.info('Замовлення #%s оплачено', order.id)
    return order
