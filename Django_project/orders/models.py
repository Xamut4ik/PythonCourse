from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from books.models import Book


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Awaiting payment')
        PAID = 'paid', _('Paid')
        CANCELLED = 'cancelled', _('Cancelled')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name=_('user'),
    )
    first_name = models.CharField(_('first name'), max_length=50)
    last_name = models.CharField(_('last name'), max_length=50)
    email = models.EmailField(_('email'))
    address = models.CharField(_('address'), max_length=250)
    city = models.CharField(_('city'), max_length=100)
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    stripe_session_id = models.CharField(_('Stripe session ID'), max_length=255, blank=True)
    stripe_payment_intent = models.CharField(_('Stripe payment intent'), max_length=255, blank=True)
    created = models.DateTimeField(_('created'), auto_now_add=True)
    updated = models.DateTimeField(_('updated'), auto_now=True)

    class Meta:
        ordering = ['-created']
        indexes = [models.Index(fields=['-created'])]
        verbose_name = _('order')
        verbose_name_plural = _('orders')

    def __str__(self):
        return _('Order #%(id)s') % {'id': self.pk}

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    def get_total_cost(self):
        return sum((item.get_cost() for item in self.items.all()), Decimal('0'))


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name=_('order'))
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name='order_items', verbose_name=_('book'))
    price = models.DecimalField(_('price'), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_('quantity'), default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = _('order item')
        verbose_name_plural = _('order items')

    def __str__(self):
        return f'{self.book} x {self.quantity}'

    def get_cost(self):
        return self.price * self.quantity
