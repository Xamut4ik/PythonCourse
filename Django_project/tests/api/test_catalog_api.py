from decimal import Decimal

import pytest

from books.models import Book, Category
from tests.factories import BookFactory, CategoryFactory, OrderItemFactory

pytestmark = [pytest.mark.api, pytest.mark.django_db]


def ids(response):
    return [item['id'] for item in response.data['results']]


def test_book_list_is_public_with_nested_category(api_client, book):
    response = api_client.get('/api/books/')
    assert response.status_code == 200
    assert response.data['count'] == 1
    item = response.data['results'][0]
    assert item['title'] == 'Кобзар'
    assert item['in_stock'] is True
    assert item['category'] == {'id': book.category.id, 'name': 'Класика', 'slug': 'classic'}
    assert 'category_id' not in item


def test_book_list_uses_single_query(api_client, django_assert_num_queries):
    BookFactory.create_batch(5)
    with django_assert_num_queries(2):
        assert api_client.get('/api/books/').status_code == 200


def test_book_retrieve(api_client, book):
    response = api_client.get(f'/api/books/{book.pk}/')
    assert response.status_code == 200
    assert response.data['price'] == '250.50'


def test_book_retrieve_missing_is_404(api_client, db):
    assert api_client.get('/api/books/999/').status_code == 404


def test_books_are_paginated_by_20(api_client):
    BookFactory.create_batch(25)
    first = api_client.get('/api/books/')
    assert first.data['count'] == 25
    assert len(first.data['results']) == 20
    assert first.data['next'] is not None
    second = api_client.get('/api/books/', {'page': 2})
    assert len(second.data['results']) == 5
    assert second.data['next'] is None


def test_admin_creates_book_with_category_id(admin_api, category):
    payload = {
        'title': 'Енеїда', 'author': 'Котляревський', 'description': 'Поема',
        'price': '120.00', 'stock': 4, 'category_id': category.pk,
    }
    response = admin_api.post('/api/books/', payload, format='json')
    assert response.status_code == 201
    assert response.data['category']['slug'] == 'classic'
    assert Book.objects.get(title='Енеїда').category == category


@pytest.mark.parametrize('field, value', [('price', '-1.00'), ('stock', -3), ('category_id', 999)])
def test_book_validation(admin_api, category, field, value):
    payload = {
        'title': 'Енеїда', 'author': 'Котляревський', 'description': 'Поема',
        'price': '120.00', 'stock': 4, 'category_id': category.pk, field: value,
    }
    response = admin_api.post('/api/books/', payload, format='json')
    assert response.status_code == 400
    assert field in response.data


def test_zero_price_is_allowed(admin_api, category):
    payload = {'title': 'Безкоштовна', 'author': 'А', 'description': '-', 'price': '0', 'stock': 1, 'category_id': category.pk}
    assert admin_api.post('/api/books/', payload, format='json').status_code == 201


def test_regular_user_cannot_modify_books(user_api, book):
    assert user_api.post('/api/books/', {}, format='json').status_code == 403
    assert user_api.patch(f'/api/books/{book.pk}/', {'price': '1.00'}, format='json').status_code == 403
    assert user_api.delete(f'/api/books/{book.pk}/').status_code == 403


def test_anonymous_cannot_modify_books(api_client, book):
    assert api_client.post('/api/books/', {}, format='json').status_code == 401
    assert api_client.delete(f'/api/books/{book.pk}/').status_code == 401


def test_admin_updates_and_deletes_book(admin_api, book):
    response = admin_api.patch(f'/api/books/{book.pk}/', {'price': '300.00'}, format='json')
    assert response.status_code == 200
    assert response.data['price'] == '300.00'
    assert admin_api.delete(f'/api/books/{book.pk}/').status_code == 204
    assert not Book.objects.filter(pk=book.pk).exists()


def test_ordered_book_cannot_be_deleted(admin_api):
    item = OrderItemFactory()
    assert admin_api.delete(f'/api/books/{item.book.pk}/').status_code == 409
    assert Book.objects.filter(pk=item.book.pk).exists()


def test_book_filters(api_client):
    poetry, prose = CategoryFactory(slug='poetry'), CategoryFactory(slug='prose')
    cheap = BookFactory(category=poetry, author='Леся Українка', price=Decimal('50'), stock=0)
    middle = BookFactory(category=poetry, author='Іван Франко', price=Decimal('150'), stock=2)
    expensive = BookFactory(category=prose, author='Іван Франко', price=Decimal('500'), stock=1)

    assert set(ids(api_client.get('/api/books/', {'category': poetry.pk}))) == {cheap.pk, middle.pk}
    assert set(ids(api_client.get('/api/books/', {'category_slug': 'prose'}))) == {expensive.pk}
    assert set(ids(api_client.get('/api/books/', {'author': 'Франко'}))) == {middle.pk, expensive.pk}
    assert set(ids(api_client.get('/api/books/', {'min_price': 100, 'max_price': 200}))) == {middle.pk}
    assert set(ids(api_client.get('/api/books/', {'in_stock': 'true'}))) == {middle.pk, expensive.pk}
    assert set(ids(api_client.get('/api/books/', {'in_stock': 'false'}))) == {cheap.pk}


def test_book_search_and_ordering(api_client):
    kobzar = BookFactory(title='Кобзар', price=Decimal('100'))
    zakhar = BookFactory(title='Захар Беркут', price=Decimal('300'))
    BookFactory(title='Лісова пісня', price=Decimal('200'))
    assert ids(api_client.get('/api/books/', {'search': 'Кобз'})) == [kobzar.pk]
    ordered = ids(api_client.get('/api/books/', {'ordering': '-price'}))
    assert ordered[0] == zakhar.pk and ordered[-1] == kobzar.pk


def test_category_list_with_books_count(api_client, book, book2):
    CategoryFactory(name='Порожня')
    response = api_client.get('/api/categories/')
    assert response.status_code == 200
    counts = {item['name']: item['books_count'] for item in response.data['results']}
    assert counts == {'Класика': 2, 'Порожня': 0}


def test_admin_category_crud(admin_api):
    created = admin_api.post('/api/categories/', {'name': 'Драма', 'slug': 'drama'}, format='json')
    assert created.status_code == 201
    assert created.data['books_count'] == 0
    pk = created.data['id']
    assert admin_api.patch(f'/api/categories/{pk}/', {'name': 'Драматургія'}, format='json').data['name'] == 'Драматургія'
    assert admin_api.delete(f'/api/categories/{pk}/').status_code == 204
    assert not Category.objects.filter(pk=pk).exists()


def test_category_slug_must_be_unique(admin_api, category):
    response = admin_api.post('/api/categories/', {'name': 'Інша', 'slug': 'classic'}, format='json')
    assert response.status_code == 400
    assert 'slug' in response.data


def test_regular_user_cannot_create_category(user_api):
    assert user_api.post('/api/categories/', {'name': 'X', 'slug': 'x'}, format='json').status_code == 403


def test_category_can_keep_its_slug_on_update(admin_api, category):
    response = admin_api.put(f'/api/categories/{category.pk}/', {'name': 'Класика UA', 'slug': 'classic'}, format='json')
    assert response.status_code == 200
    assert response.data['slug'] == 'classic'
