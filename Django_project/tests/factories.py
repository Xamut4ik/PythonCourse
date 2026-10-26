from decimal import Decimal

import factory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from books.models import Book, Category
from orders.models import Order, OrderItem

PASSWORD = 'pass12345'


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ('username',)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda u: f'{u.username}@example.com')
    first_name = 'Тарас'
    last_name = 'Шевченко'
    password = factory.django.Password(PASSWORD)


class GroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Group
        django_get_or_create = ('name',)
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f'group{n}')

    @factory.post_generation
    def permissions(self, create, codenames, **kwargs):
        if create and codenames:
            self.permissions.add(*Permission.objects.filter(codename__in=codenames))


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f'Категорія {n}')
    slug = factory.Sequence(lambda n: f'category-{n}')


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f'Книга {n}')
    author = factory.Faker('name', locale='uk_UA')
    price = Decimal('250.50')
    description = factory.Faker('sentence')
    stock = 5
    category = factory.SubFactory(CategoryFactory)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    first_name = 'Тарас'
    last_name = 'Шевченко'
    email = factory.Sequence(lambda n: f'buyer{n}@example.com')
    address = 'вул. Хрещатик, 1'
    city = 'Київ'


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    book = factory.SubFactory(BookFactory)
    price = factory.LazyAttribute(lambda item: item.book.price)
    quantity = 1
