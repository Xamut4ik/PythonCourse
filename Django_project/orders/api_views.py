from django.db import transaction
from django.db.models import Prefetch
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsOwnerOrReadOnly
from .filters import OrderFilter
from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    CartItemSerializer, CartSerializer, OrderContactSerializer, OrderSerializer, OrderUpdateSerializer,
)
from .services import OrderError, create_order, restore_order_stock


class OwnedQuerysetMixin:
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    owner_lookup = 'user'

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        user = self.request.user
        if user.is_staff:
            return queryset
        return queryset.filter(**{self.owner_lookup: user})


@extend_schema_view(
    list=extend_schema(
        summary='Список замовлень',
        description=(
            'Звичайний користувач бачить тільки свої замовлення, адміністратор — усі. '
            'Фільтри: `status`, `created_after`, `created_before` (YYYY-MM-DD). '
            'Пошук `search` за ім\'ям, прізвищем, email і містом. Сортування `ordering`: `created`, `status`.'
        ),
    ),
    retrieve=extend_schema(summary='Замовлення', description='Замовлення з вкладеними позиціями та сумою.'),
    create=extend_schema(
        summary='Створити замовлення',
        description=(
            'Позиції передаються в `items` як `[{"book_id": 1, "quantity": 2}]`. Ціна фіксується на момент '
            'замовлення, залишок на складі списується. Якщо книги не вистачає — 400.'
        ),
    ),
    update=extend_schema(
        summary='Оновити замовлення',
        description=(
            'Власник може змінити контактні дані, поки замовлення очікує оплати. Позиції змінити не можна. '
            'Статус змінює тільки адміністратор; при скасуванні залишок повертається на склад, '
            'скасоване замовлення повторно відкрити не можна.'
        ),
    ),
    partial_update=extend_schema(summary='Частково оновити замовлення', description='Ті самі правила, що й для PUT.'),
    destroy=extend_schema(
        summary='Видалити замовлення',
        description=(
            'Власник може видалити скасоване замовлення або замовлення, що очікує оплати, '
            'якщо оплату через Stripe ще не розпочато; інакше 403. Адміністратор може видалити будь-яке. '
            'Для замовлення, що очікує оплати, залишок повертається на склад.'
        ),
    ),
)
class OrderViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Order.objects.select_related('user').prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related('book'))
    )
    serializer_class = OrderSerializer
    filterset_class = OrderFilter
    search_fields = ['first_name', 'last_name', 'email', 'city']
    ordering_fields = ['created', 'status']
    ordering = ['-created']

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return OrderUpdateSerializer
        return OrderSerializer

    def perform_destroy(self, instance):
        deletable = instance.status == Order.Status.CANCELLED or (
            instance.status == Order.Status.PENDING and not instance.stripe_session_id
        )
        if not deletable and not self.request.user.is_staff:
            raise PermissionDenied(_('This order can no longer be deleted.'))
        with transaction.atomic():
            if instance.status == Order.Status.PENDING:
                restore_order_stock(instance)
            instance.delete()


@extend_schema_view(
    list=extend_schema(
        summary='Кошики',
        description='Звичайний користувач бачить тільки свій кошик (не більше одного), адміністратор — усі.',
    ),
    retrieve=extend_schema(summary='Кошик', description='Кошик з вкладеними позиціями і загальною сумою.'),
    create=extend_schema(
        summary='Створити кошик',
        description='Створює кошик поточного користувача, можна одразу з `items`. Другий кошик створити не можна.',
    ),
    update=extend_schema(
        summary='Замінити вміст кошика',
        description='Якщо передано `items`, усі позиції кошика замінюються новими.',
    ),
    partial_update=extend_schema(summary='Частково оновити кошик', description='Ті самі правила, що й для PUT.'),
    destroy=extend_schema(summary='Видалити кошик', description='Видаляє кошик разом з усіма позиціями.'),
)
class CartViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Cart.objects.select_related('user').prefetch_related(
        Prefetch('items', queryset=CartItem.objects.select_related('book').order_by('pk'))
    ).order_by('pk')
    serializer_class = CartSerializer
    filter_backends = []

    @extend_schema(
        summary='Оформити замовлення з кошика',
        description=(
            'Створює замовлення з усіх позицій кошика з вказаними контактними даними і очищає кошик. '
            'Повертає створене замовлення. Порожній кошик або нестача книг — 400.'
        ),
        request=OrderContactSerializer,
        responses={201: OrderSerializer},
    )
    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        cart = self.get_object()
        contact = OrderContactSerializer(data=request.data)
        contact.is_valid(raise_exception=True)
        items = [(item.book_id, item.quantity) for item in cart.items.all()]
        with transaction.atomic():
            try:
                order = create_order(cart.user, contact.validated_data, items)
            except OrderError as e:
                raise ValidationError({'detail': str(e)})
            cart.items.all().delete()
        order = Order.objects.prefetch_related('items__book').get(pk=order.pk)
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        summary='Позиції кошика',
        description='Позиції кошика поточного користувача (адміністратор бачить усі). Пошук `search` за назвою книги.',
    ),
    retrieve=extend_schema(summary='Позиція кошика', description='Одна позиція з вкладеною книгою.'),
    create=extend_schema(
        summary='Додати книгу в кошик',
        description=(
            'Додає книгу в кошик поточного користувача (кошик створюється автоматично). '
            'Кількість має бути більшою за 0 і не перевищувати залишок. Книгу, яка вже є в кошику, додати повторно не можна.'
        ),
    ),
    update=extend_schema(summary='Змінити позицію', description='Зміна книги або кількості.'),
    partial_update=extend_schema(summary='Змінити кількість', description='Зазвичай передається тільки `quantity`.'),
    destroy=extend_schema(summary='Прибрати з кошика', description='Видаляє позицію з кошика.'),
)
class CartItemViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = CartItem.objects.select_related('book', 'cart').order_by('pk')
    serializer_class = CartItemSerializer
    owner_lookup = 'cart__user'
    owner_field = 'cart.user_id'
    search_fields = ['book__title']
    ordering_fields = ['quantity']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = getattr(self.request, 'user', None)
        if user is not None and user.is_authenticated:
            context['cart'] = Cart.objects.filter(user=user).first()
        return context

    def perform_create(self, serializer):
        cart, _created = Cart.objects.get_or_create(user=self.request.user)
        serializer.save(cart=cart)
