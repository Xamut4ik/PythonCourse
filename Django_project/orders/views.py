import logging

import stripe
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView

from books.models import Book
from .cart import Cart
from .forms import CartAddBookForm, OrderCreateForm
from .models import Order
from .services import OrderError, create_checkout_session, create_order_from_cart, mark_order_paid

logger = logging.getLogger(__name__)

SESSION_ORDER_IDS = 'order_ids'


def get_own_order(request, pk):
    """Повертає замовлення ``pk``, якщо воно належить поточному відвідувачу.

    Замовлення вважається своїм, якщо його id збережено в сесії (гість) або
    воно прив'язане до автентифікованого користувача.

    Args:
        request: поточний HttpRequest.
        pk: первинний ключ замовлення.

    Returns:
        Order.

    Raises:
        Http404: замовлення не існує або належить іншому користувачу.
    """
    order = get_object_or_404(Order, pk=pk)
    own_by_session = pk in request.session.get(SESSION_ORDER_IDS, [])
    own_by_user = request.user.is_authenticated and order.user_id == request.user.id
    if not (own_by_session or own_by_user):
        raise Http404
    return order


class CartDetail(TemplateView):
    """Вміст кошика з сесії.

    Повертає HTML-сторінку ``orders/cart_detail.html`` з ``items``: кожен елемент містить
    ``book``, ``quantity``, ``price``, ``total_price`` і форму оновлення ``update_form``.
    Права доступу: доступно всім (кошик прив'язаний до сесії).
    """

    template_name = 'orders/cart_detail.html'

    def get_context_data(self, **kwargs):
        """Додає до контексту позиції кошика з формами зміни кількості."""
        context = super().get_context_data(**kwargs)
        items = list(Cart(self.request))
        for item in items:
            item['update_form'] = CartAddBookForm(
                initial={'quantity': item['quantity'], 'override': True}
            )
        context['items'] = items
        return context


class CartAdd(View):
    """Додавання книги в кошик або зміна її кількості (тільки POST).

    Параметри URL:
        book_id: первинний ключ книги.

    POST-дані (``CartAddBookForm``):
        quantity: кількість від 1 до 20.
        override: якщо true, кількість замінюється, інакше додається до наявної.

    Повертає redirect на кошик з flash-повідомленням; 404, якщо книги немає; 405 для GET.
    Права доступу: доступно всім.
    """

    def post(self, request, book_id):
        """Перевіряє форму і залишок на складі та оновлює кошик у сесії."""
        book = get_object_or_404(Book, pk=book_id)
        form = CartAddBookForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Invalid quantity.'))
            return redirect('orders:cart_detail')

        cart = Cart(request)
        quantity = form.cleaned_data['quantity']
        override = form.cleaned_data['override']
        wanted = quantity if override else cart.get_quantity(book) + quantity
        if wanted > book.stock:
            messages.error(request, _('Only %(stock)s copies of "%(title)s" are in stock.') % {
                'stock': book.stock, 'title': book.title,
            })
            return redirect('orders:cart_detail')

        cart.add(book, quantity=quantity, override_quantity=override)
        messages.success(request, _('"%(title)s" added to the cart.') % {'title': book.title})
        return redirect('orders:cart_detail')


class CartRemove(View):
    """Видалення книги з кошика (тільки POST).

    Параметри URL:
        book_id: первинний ключ книги.

    Повертає redirect на кошик або 404, якщо книги немає. Права доступу: доступно всім.
    """

    def post(self, request, book_id):
        """Прибирає книгу з кошика в сесії."""
        book = get_object_or_404(Book, pk=book_id)
        Cart(request).remove(book)
        return redirect('orders:cart_detail')


class CartClear(View):
    """Очищення кошика (тільки POST).

    Повертає redirect на кошик. Права доступу: доступно всім.
    """

    def post(self, request):
        """Видаляє всі позиції з кошика в сесії."""
        Cart(request).clear()
        return redirect('orders:cart_detail')


class OrderCreate(FormView):
    """Оформлення замовлення з поточного кошика.

    GET показує форму ``OrderCreateForm`` (для автентифікованого користувача
    з передзаповненими ім'ям, прізвищем і email). POST створює замовлення,
    списує залишки, очищає кошик і перенаправляє на оплату.

    Повертає HTML-сторінку ``orders/order_create.html`` або redirect: на кошик,
    якщо він порожній чи товару не вистачає, на ``orders:pay`` після успіху.
    Права доступу: доступно всім, зокрема гостям.
    """

    form_class = OrderCreateForm
    template_name = 'orders/order_create.html'

    def dispatch(self, request, *args, **kwargs):
        """Перенаправляє на кошик, якщо він порожній, інакше передає запит далі."""
        if not len(Cart(request)):
            messages.info(request, _('Your cart is empty.'))
            return redirect('orders:cart_detail')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Повертає початкові дані форми з профілю автентифікованого користувача або ``{}``."""
        user = self.request.user
        if user.is_authenticated:
            return {'first_name': user.first_name, 'last_name': user.last_name, 'email': user.email}
        return {}

    def form_valid(self, form):
        """Створює замовлення, запам'ятовує його id у сесії і повертає redirect на оплату."""
        cart = Cart(self.request)
        try:
            order = create_order_from_cart(cart, form, self.request.user)
        except OrderError as e:
            messages.error(self.request, str(e))
            return redirect('orders:cart_detail')

        cart.clear()
        self.request.session[SESSION_ORDER_IDS] = [
            *self.request.session.get(SESSION_ORDER_IDS, []), order.id
        ]
        logger.info('Створено %s', order)
        return redirect('orders:pay', pk=order.id)


class OrderPay(View):
    """Перехід до оплати замовлення через Stripe Checkout.

    Параметри URL:
        pk: первинний ключ замовлення.

    Повертає redirect на сторінку Stripe; на список книг, якщо замовлення вже не
    очікує оплати; на ``orders:payment_cancel``, якщо Stripe недоступний; 404 для чужого замовлення.
    Права доступу: власник замовлення (за сесією або користувачем).
    """

    def get(self, request, pk):
        """Створює Checkout Session і перенаправляє на неї."""
        order = get_own_order(request, pk)
        if order.status != Order.Status.PENDING:
            messages.info(request, _('%(order)s is no longer awaiting payment.') % {'order': order})
            return redirect('books:list')
        try:
            session = create_checkout_session(order, request)
        except stripe.StripeError:
            logger.exception('Не вдалося створити Stripe Checkout Session для %s', order)
            messages.error(request, _('Could not proceed to payment. Please try again later.'))
            return redirect('orders:payment_cancel', pk=order.id)
        return redirect(session.url, permanent=False)


class PaymentSuccess(TemplateView):
    """Сторінка, на яку Stripe повертає покупця після оплати.

    GET-параметри:
        session_id: id Stripe Checkout Session.

    Перевіряє сесію через Stripe API, позначає замовлення оплаченим (якщо
    ``payment_status == 'paid'``) і показує ``orders/payment_success.html`` з ``order``.
    Повертає 404, якщо ``session_id`` відсутній, невідомий Stripe, не містить
    коректного id замовлення або замовлення чуже.
    Права доступу: власник замовлення.
    """

    template_name = 'orders/payment_success.html'

    def get_context_data(self, **kwargs):
        """Отримує Checkout Session зі Stripe і додає до контексту ``order``."""
        context = super().get_context_data(**kwargs)
        session_id = self.request.GET.get('session_id')
        if not session_id:
            raise Http404
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            raise Http404
        try:
            order_id = int(session.client_reference_id)
        except (TypeError, ValueError):
            raise Http404
        mark_order_paid(session)
        context['order'] = get_own_order(self.request, order_id)
        return context


class PaymentCancel(TemplateView):
    """Сторінка скасованої або невдалої оплати.

    Параметри URL:
        pk: первинний ключ замовлення.

    Повертає HTML-сторінку ``orders/payment_cancel.html`` з ``order`` або 404 для чужого замовлення.
    Права доступу: власник замовлення.
    """

    template_name = 'orders/payment_cancel.html'

    def get_context_data(self, **kwargs):
        """Додає до контексту замовлення поточного відвідувача."""
        context = super().get_context_data(**kwargs)
        context['order'] = get_own_order(self.request, kwargs['pk'])
        return context


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhook(View):
    """Приймає webhook-події від Stripe (тільки POST, без CSRF).

    Перевіряє підпис заголовка ``Stripe-Signature`` секретом ``STRIPE_WEBHOOK_SECRET``.
    Для ``checkout.session.completed`` і ``checkout.session.async_payment_succeeded``
    позначає замовлення оплаченим.

    Повертає 200 для прийнятої події, 400 для невалідного тіла чи підпису.
    Права доступу: публічний endpoint, автентифікація через підпис Stripe.
    """

    def post(self, request):
        """Верифікує подію і обробляє оплату."""
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                request.headers.get('Stripe-Signature', ''),
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.SignatureVerificationError):
            return HttpResponse(status=400)

        if event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
            mark_order_paid(event['data']['object'])
        return HttpResponse(status=200)
