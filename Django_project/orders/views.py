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
    """Повертає замовлення лише його власнику: автору сесії або користувачу, що його створив."""
    order = get_object_or_404(Order, pk=pk)
    own_by_session = pk in request.session.get(SESSION_ORDER_IDS, [])
    own_by_user = request.user.is_authenticated and order.user_id == request.user.id
    if not (own_by_session or own_by_user):
        raise Http404
    return order


class CartDetail(TemplateView):
    template_name = 'orders/cart_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(Cart(self.request))
        for item in items:
            item['update_form'] = CartAddBookForm(
                initial={'quantity': item['quantity'], 'override': True}
            )
        context['items'] = items
        return context


class CartAdd(View):
    def post(self, request, book_id):
        book = get_object_or_404(Book, pk=book_id)
        cart = Cart(request)
        form = CartAddBookForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Invalid quantity.'))
            return redirect('orders:cart_detail')

        quantity = form.cleaned_data['quantity']
        override = form.cleaned_data['override']
        in_cart = cart.cart.get(str(book.id), {}).get('quantity', 0)
        wanted = quantity if override else in_cart + quantity
        if wanted > book.stock:
            messages.error(request, _('Only %(stock)s copies of "%(title)s" are in stock.') % {
                'stock': book.stock, 'title': book.title,
            })
        else:
            cart.add(book, quantity=quantity, override_quantity=override)
            messages.success(request, _('"%(title)s" added to the cart.') % {'title': book.title})
        return redirect('orders:cart_detail')


class CartRemove(View):
    def post(self, request, book_id):
        book = get_object_or_404(Book, pk=book_id)
        Cart(request).remove(book)
        return redirect('orders:cart_detail')


class CartClear(View):
    def post(self, request):
        Cart(request).clear()
        return redirect('orders:cart_detail')


class OrderCreate(FormView):
    form_class = OrderCreateForm
    template_name = 'orders/order_create.html'

    def dispatch(self, request, *args, **kwargs):
        if not len(Cart(request)):
            messages.info(request, _('Your cart is empty.'))
            return redirect('orders:cart_detail')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        user = self.request.user
        if user.is_authenticated:
            return {'first_name': user.first_name, 'last_name': user.last_name, 'email': user.email}
        return {}

    def form_valid(self, form):
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
    """Створює Stripe Checkout Session і перенаправляє на сторінку оплати Stripe."""

    def get(self, request, pk):
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
    template_name = 'orders/payment_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = self.request.GET.get('session_id')
        if not session_id:
            raise Http404
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            raise Http404
        # Вебхук — основне джерело істини, але підтверджуємо і тут, на випадок якщо він ще не дійшов
        mark_order_paid(session)
        context['order'] = get_own_order(self.request, int(session.client_reference_id))
        return context


class PaymentCancel(TemplateView):
    template_name = 'orders/payment_cancel.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order'] = get_own_order(self.request, kwargs['pk'])
        return context


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhook(View):
    def post(self, request):
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
