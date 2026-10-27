from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from books.models import Book, Category, CustomUser
from orders.models import Order, OrderItem
from tests.factories import BookFactory, CategoryFactory, OrderFactory, OrderItemFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class TestCategory:
    def test_create_and_str(self):
        # Generated with AI, reviewed and modified
        category = Category.objects.create(name='Фантастика', slug='sci-fi')
        assert Category.objects.get(slug='sci-fi') == category
        assert str(category) == 'Фантастика'

    def test_name_max_length(self):
        # Generated with AI, reviewed and modified
        category = Category(name='x' * 101, slug='long')
        with pytest.raises(ValidationError) as exc:
            category.full_clean()
        assert 'name' in exc.value.message_dict

    def test_slug_rejects_invalid_characters(self):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError) as exc:
            Category(name='Поезія', slug='не slug!').full_clean()
        assert 'slug' in exc.value.message_dict

    def test_slug_max_length(self):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError) as exc:
            Category(name='Поезія', slug='a' * 41).full_clean()
        assert 'slug' in exc.value.message_dict

    def test_delete_cascades_to_books(self):
        # Generated with AI, reviewed and modified
        category = CategoryFactory()
        BookFactory.create_batch(2, category=category)
        category.delete()
        assert Book.objects.count() == 0


class TestBook:
    def test_create_and_str(self):
        # Generated with AI, reviewed and modified
        category = CategoryFactory()
        book = Book.objects.create(
            title='Кобзар', author='Шевченко', price=Decimal('199.99'),
            description='Збірка поезій', stock=3, category=category,
        )
        book.refresh_from_db()
        assert str(book) == 'Кобзар'
        assert book.price == Decimal('199.99')
        assert book.category == category

    @pytest.mark.parametrize('stock, expected', [(5, True), (1, True), (0, False), (-1, False)])
    def test_in_stock(self, stock, expected):
        # Generated with AI, reviewed and modified
        assert BookFactory.build(stock=stock).in_stock is expected

    def test_valid_book_passes_full_clean(self):
        # Generated with AI, reviewed and modified
        BookFactory().full_clean()

    @pytest.mark.parametrize('field', ['title', 'author'])
    def test_char_fields_max_length(self, field):
        # Generated with AI, reviewed and modified
        book = BookFactory.build(category=CategoryFactory(), **{field: 'x' * 101})
        with pytest.raises(ValidationError) as exc:
            book.full_clean()
        assert field in exc.value.message_dict

    def test_price_decimal_places(self):
        # Generated with AI, reviewed and modified
        book = BookFactory.build(category=CategoryFactory(), price=Decimal('10.123'))
        with pytest.raises(ValidationError) as exc:
            book.full_clean()
        assert 'price' in exc.value.message_dict

    def test_price_max_digits(self):
        # Generated with AI, reviewed and modified
        book = BookFactory.build(category=CategoryFactory(), price=Decimal('123456789.00'))
        with pytest.raises(ValidationError) as exc:
            book.full_clean()
        assert 'price' in exc.value.message_dict

    @pytest.mark.parametrize('field', ['title', 'author', 'description'])
    def test_required_fields(self, field):
        # Generated with AI, reviewed and modified
        book = BookFactory.build(category=CategoryFactory(), **{field: ''})
        with pytest.raises(ValidationError) as exc:
            book.full_clean()
        assert field in exc.value.message_dict

    def test_category_is_required(self):
        # Generated with AI, reviewed and modified
        with pytest.raises(IntegrityError), transaction.atomic():
            Book.objects.create(title='Без категорії', author='А', price=1, description='-', stock=1)

    def test_reverse_relations(self):
        # Generated with AI, reviewed and modified
        book = BookFactory()
        item = OrderItemFactory(book=book)
        assert list(book.category.book_set.all()) == [book]
        assert list(book.order_items.all()) == [item]

    def test_ordered_book_cannot_be_deleted(self):
        # Generated with AI, reviewed and modified
        item = OrderItemFactory()
        with pytest.raises(ProtectedError):
            item.book.delete()

    def test_verbose_names(self):
        # Generated with AI, reviewed and modified
        assert Book._meta.verbose_name == 'книга'
        assert Book._meta.get_field('stock').help_text


class TestCustomUser:
    def test_email_is_unique(self):
        # Generated with AI, reviewed and modified
        UserFactory(username='first', email='same@example.com')
        with pytest.raises(IntegrityError), transaction.atomic():
            CustomUser.objects.create_user(username='second', email='same@example.com', password='x')

    def test_password_is_hashed(self):
        # Generated with AI, reviewed and modified
        user = CustomUser.objects.create_user(username='ivan', email='ivan@example.com', password='secret123')
        assert user.password != 'secret123'
        assert user.check_password('secret123')
        assert str(user) == 'ivan'


class TestOrder:
    def test_create_with_defaults(self):
        # Generated with AI, reviewed and modified
        order = Order.objects.create(
            first_name='Леся', last_name='Українка', email='lesia@example.com',
            address='вул. Лесі Українки, 1', city='Луцьк',
        )
        assert order.status == Order.Status.PENDING
        assert order.user is None
        assert order.stripe_session_id == ''
        assert order.stripe_payment_intent == ''
        assert order.created is not None and order.updated is not None

    def test_str_contains_pk(self):
        # Generated with AI, reviewed and modified
        order = OrderFactory()
        assert str(order) == f'Замовлення #{order.pk}'

    @pytest.mark.parametrize('status, paid', [
        (Order.Status.PENDING, False), (Order.Status.PAID, True), (Order.Status.CANCELLED, False),
    ])
    def test_is_paid(self, status, paid):
        # Generated with AI, reviewed and modified
        assert OrderFactory.build(status=status).is_paid is paid

    def test_invalid_status_rejected(self):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError) as exc:
            OrderFactory.build(status='shipped').full_clean()
        assert 'status' in exc.value.message_dict

    def test_invalid_email_rejected(self):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError) as exc:
            OrderFactory.build(email='not-an-email').full_clean()
        assert 'email' in exc.value.message_dict

    @pytest.mark.parametrize('field, limit', [('first_name', 50), ('last_name', 50), ('address', 250), ('city', 100)])
    def test_char_fields_max_length(self, field, limit):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError) as exc:
            OrderFactory.build(**{field: 'x' * (limit + 1)}).full_clean()
        assert field in exc.value.message_dict

    def test_get_total_cost(self):
        # Generated with AI, reviewed and modified
        order = OrderFactory()
        OrderItemFactory(order=order, price=Decimal('120.00'), quantity=3)
        OrderItemFactory(order=order, price=Decimal('0.99'), quantity=1)
        assert order.get_total_cost() == Decimal('360.99')

    def test_ordering_newest_first(self):
        # Generated with AI, reviewed and modified
        first, second = OrderFactory(), OrderFactory()
        Order.objects.filter(pk=first.pk).update(created=second.created - timedelta(hours=1))
        assert list(Order.objects.all()) == [second, first]

    def test_user_delete_keeps_order(self):
        # Generated with AI, reviewed and modified
        user = UserFactory()
        order = OrderFactory(user=user)
        user.delete()
        order.refresh_from_db()
        assert order.user is None

    def test_delete_cascades_to_items(self):
        # Generated with AI, reviewed and modified
        order = OrderFactory()
        OrderItemFactory.create_batch(2, order=order)
        order.delete()
        assert OrderItem.objects.count() == 0


class TestOrderItem:
    def test_create_str_and_cost(self):
        # Generated with AI, reviewed and modified
        item = OrderItemFactory(book=BookFactory(title='Енеїда'), price=Decimal('75.50'), quantity=2)
        assert str(item) == 'Енеїда x 2'
        assert item.get_cost() == Decimal('151.00')

    def test_default_quantity_is_one(self):
        # Generated with AI, reviewed and modified
        book = BookFactory()
        item = OrderItem.objects.create(order=OrderFactory(), book=book, price=book.price)
        assert item.quantity == 1

    def test_quantity_must_be_positive(self):
        # Generated with AI, reviewed and modified
        item = OrderItemFactory.build(order=OrderFactory(), book=BookFactory(), price=Decimal('1.00'), quantity=0)
        with pytest.raises(ValidationError) as exc:
            item.full_clean()
        assert 'quantity' in exc.value.message_dict

    def test_price_is_snapshot_of_book_price(self):
        # Generated with AI, reviewed and modified
        book = BookFactory(price=Decimal('100.00'))
        item = OrderItemFactory(book=book)
        book.price = Decimal('150.00')
        book.save()
        item.refresh_from_db()
        assert item.price == Decimal('100.00')
