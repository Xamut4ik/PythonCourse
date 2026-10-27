import inspect

import pytest
from asgiref.sync import sync_to_async
from django.urls import reverse

from books import async_views
from orders import async_views as orders_async_views
from orders.models import Order
from tests.factories import BookFactory, CategoryFactory, OrderFactory, OrderItemFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('view', [
    async_views.catalog_stats,
    async_views.category_books,
    async_views.book_api,
    orders_async_views.order_status,
])
def test_views_are_coroutines(view):
    assert inspect.iscoroutinefunction(view)


@pytest.mark.django_db
def test_catalog_stats_context(client, category):
    empty = CategoryFactory(name='Порожня')
    BookFactory(category=category, stock=3)
    BookFactory(category=category, stock=0)

    response = client.get(reverse('books:stats'))

    assert response.status_code == 200
    assert 'books/catalog_stats.html' in [t.name for t in response.templates]
    ctx = response.context
    assert (ctx['books_count'], ctx['categories_count'], ctx['out_of_stock_count'], ctx['total_stock']) == (2, 2, 1, 3)
    assert {c.name: c.book_count for c in ctx['categories']} == {'Класика': 2, empty.name: 0}
    assert '2 книги' in response.content.decode()


@pytest.mark.django_db
def test_category_books(client, category, book):
    BookFactory()
    response = client.get(reverse('books:category', args=[category.slug]))
    assert response.status_code == 200
    assert response.context['category'] == category
    assert list(response.context['books']) == [book]


@pytest.mark.django_db
def test_category_books_404(client):
    assert client.get(reverse('books:category', args=['missing'])).status_code == 404


@pytest.mark.django_db
def test_book_api(client, book):
    response = client.get(reverse('books:api_detail', args=[book.pk]))
    assert response.json() == {
        'id': book.pk, 'title': 'Кобзар', 'author': 'Шевченко', 'price': '250.50',
        'stock': 5, 'in_stock': True, 'category': 'Класика',
    }


@pytest.mark.django_db
def test_book_api_404(client):
    response = client.get(reverse('books:api_detail', args=[999]))
    assert response.status_code == 404
    assert response.json() == {'error': 'not found'}


@pytest.mark.django_db
def test_order_status_for_account_owner(auth_client, user):
    order = OrderFactory(user=user)
    OrderItemFactory(order=order, book=BookFactory(title='Кобзар'), quantity=2)

    response = auth_client.get(reverse('orders:order_status', args=[order.pk]))

    data = response.json()
    assert data['status'] == 'pending'
    assert data['status_display'] == 'Очікує оплати'
    assert data['total'] == '501.00'
    assert data['items'] == [{'title': 'Кобзар', 'quantity': 2, 'price': '250.50'}]


@pytest.mark.django_db
def test_order_status_hidden_from_strangers(client):
    order = OrderFactory()
    assert client.get(reverse('orders:order_status', args=[order.pk])).status_code == 404
    assert client.get(reverse('orders:order_status', args=[999])).status_code == 404


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_book_api_with_async_client(async_client):
    category = await CategoryFactory._meta.model.objects.acreate(name='Драма', slug='drama')
    book = await sync_to_async(BookFactory)(title='Лісова пісня', category=category)

    response = await async_client.get(reverse('books:api_detail', args=[book.pk]))

    assert response.status_code == 200
    assert response.json()['title'] == 'Лісова пісня'
    assert await Order.objects.acount() == 0
