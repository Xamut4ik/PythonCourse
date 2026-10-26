from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from books.models import Book


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікує оплати'
        PAID = 'paid', 'Оплачено'
        CANCELLED = 'cancelled', 'Скасовано'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    first_name = models.CharField('Імʼя', max_length=50)
    last_name = models.CharField('Прізвище', max_length=50)
    email = models.EmailField('Email')
    address = models.CharField('Адреса', max_length=250)
    city = models.CharField('Місто', max_length=100)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    stripe_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']
        indexes = [models.Index(fields=['-created'])]
        verbose_name = 'Замовлення'
        verbose_name_plural = 'Замовлення'

    def __str__(self):
        return f'Замовлення #{self.pk}'

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    def get_total_cost(self):
        return sum((item.get_cost() for item in self.items.all()), Decimal('0'))


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name='order_items')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Позиція замовлення'
        verbose_name_plural = 'Позиції замовлення'

    def __str__(self):
        return f'{self.book} x {self.quantity}'

    def get_cost(self):
        return self.price * self.quantity
