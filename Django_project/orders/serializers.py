from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from books.models import Book
from books.serializers import BookShortSerializer
from .models import Cart, CartItem, Order, OrderItem
from .services import OrderError, create_order, restore_order_stock

CONTACT_FIELDS = ['first_name', 'last_name', 'email', 'address', 'city']


def validate_unique_books(items):
    book_ids = [item['book'].pk for item in items]
    if len(book_ids) != len(set(book_ids)):
        raise serializers.ValidationError(_('Each book can appear only once.'))
    return items


def validate_quantity_in_stock(book, quantity):
    if quantity > book.stock:
        raise serializers.ValidationError(
            {'quantity': _('Only %(stock)s copies of "%(title)s" are in stock.') % {
                'stock': book.stock, 'title': book.title,
            }}
        )


class OrderItemSerializer(serializers.ModelSerializer):
    book = BookShortSerializer(read_only=True)
    book_id = serializers.PrimaryKeyRelatedField(source='book', queryset=Book.objects.all(), write_only=True)
    quantity = serializers.IntegerField(min_value=1)
    cost = serializers.DecimalField(source='get_cost', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'book', 'book_id', 'price', 'quantity', 'cost']
        read_only_fields = ['price']


class OrderSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    items = OrderItemSerializer(many=True)
    is_paid = serializers.BooleanField(read_only=True)
    total_cost = serializers.DecimalField(source='get_total_cost', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'user', *CONTACT_FIELDS, 'status', 'is_paid', 'items', 'total_cost', 'created', 'updated']
        read_only_fields = ['created', 'updated']

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(_('An order must contain at least one item.'))
        return validate_unique_books(items)

    def validate_status(self, value):
        if self.instance is None:
            if value != Order.Status.PENDING:
                raise serializers.ValidationError(_('A new order always awaits payment.'))
        elif value != self.instance.status:
            if not self.context['request'].user.is_staff:
                raise serializers.ValidationError(_('Only an administrator can change the order status.'))
            if self.instance.status == Order.Status.CANCELLED:
                raise serializers.ValidationError(_('A cancelled order cannot be reopened.'))
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        if self.instance is not None and not user.is_staff and self.instance.status != Order.Status.PENDING:
            raise serializers.ValidationError(_('Only orders awaiting payment can be changed.'))
        return attrs

    def create(self, validated_data):
        items = validated_data.pop('items')
        validated_data.pop('status', None)
        try:
            order = create_order(
                self.context['request'].user,
                validated_data,
                [(item['book'].pk, item['quantity']) for item in items],
            )
        except OrderError as e:
            raise serializers.ValidationError({'items': [str(e)]})
        return Order.objects.prefetch_related('items__book').get(pk=order.pk)

    def update(self, instance, validated_data):
        new_status = validated_data.get('status', instance.status)
        with transaction.atomic():
            if instance.status == Order.Status.PENDING and new_status == Order.Status.CANCELLED:
                restore_order_stock(instance)
            return super().update(instance, validated_data)


class OrderUpdateSerializer(OrderSerializer):
    items = OrderItemSerializer(many=True, read_only=True)


class OrderContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = CONTACT_FIELDS


class CartItemSerializer(serializers.ModelSerializer):
    book = BookShortSerializer(read_only=True)
    book_id = serializers.PrimaryKeyRelatedField(source='book', queryset=Book.objects.all(), write_only=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    cost = serializers.DecimalField(source='get_cost', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'book', 'book_id', 'quantity', 'cost']

    def validate(self, attrs):
        book = attrs.get('book', getattr(self.instance, 'book', None))
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', 1))
        validate_quantity_in_stock(book, quantity)
        if self.parent is None:
            cart = self.instance.cart if self.instance is not None else self.context.get('cart')
            if cart is not None:
                duplicates = cart.items.filter(book=book)
                if self.instance is not None:
                    duplicates = duplicates.exclude(pk=self.instance.pk)
                if duplicates.exists():
                    raise serializers.ValidationError(
                        {'book_id': _('This book is already in the cart. Change its quantity instead.')}
                    )
        return attrs


class CartSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    items = CartItemSerializer(many=True, required=False)
    total_price = serializers.DecimalField(source='get_total_price', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total_price', 'created', 'updated']
        read_only_fields = ['created', 'updated']

    def validate_items(self, items):
        return validate_unique_books(items)

    def validate(self, attrs):
        user = self.context['request'].user
        if self.instance is None and Cart.objects.filter(user=user).exists():
            raise serializers.ValidationError(_('You already have a cart.'))
        return attrs

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        with transaction.atomic():
            cart = Cart.objects.create(user=self.context['request'].user)
            self._set_items(cart, items)
        return Cart.objects.prefetch_related('items__book').get(pk=cart.pk)

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        with transaction.atomic():
            if items is not None:
                instance.items.all().delete()
                self._set_items(instance, items)
            instance.save(update_fields=['updated'])
        return instance

    def _set_items(self, cart, items):
        CartItem.objects.bulk_create(
            CartItem(cart=cart, book=item['book'], quantity=item['quantity']) for item in items
        )
