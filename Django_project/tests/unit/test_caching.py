from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from books.cache import book_detail_key, get_catalog_version
from books.models import Book
from tests.factories import BookFactory, CategoryFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def api_client():
    return APIClient()


def test_book_detail_second_request_is_served_from_cache(api_client, book, django_assert_num_queries):
    first = api_client.get(f'/api/books/{book.pk}/')
    assert first.status_code == 200
    assert cache.get(book_detail_key(book.pk)) == first.data
    with django_assert_num_queries(0):
        second = api_client.get(f'/api/books/{book.pk}/')
    assert second.data == first.data


def test_cached_book_detail_ignores_changes_without_signals(api_client, book):
    api_client.get(f'/api/books/{book.pk}/')
    Book.objects.filter(pk=book.pk).update(title='Змінено в обхід сигналів')
    assert api_client.get(f'/api/books/{book.pk}/').data['title'] == 'Кобзар'


def test_book_save_invalidates_detail_cache(api_client, book):
    api_client.get(f'/api/books/{book.pk}/')
    book.price = Decimal('999.00')
    book.save()
    assert cache.get(book_detail_key(book.pk)) is None
    assert api_client.get(f'/api/books/{book.pk}/').data['price'] == '999.00'


def test_book_delete_invalidates_detail_cache(api_client, book):
    api_client.get(f'/api/books/{book.pk}/')
    book_id = book.pk
    book.delete()
    assert cache.get(book_detail_key(book_id)) is None
    assert api_client.get(f'/api/books/{book_id}/').status_code == 404


def test_category_change_invalidates_books_of_category(api_client, book):
    api_client.get(f'/api/books/{book.pk}/')
    book.category.name = 'Нова класика'
    book.category.save()
    assert api_client.get(f'/api/books/{book.pk}/').data['category']['name'] == 'Нова класика'


def test_api_book_list_is_page_cached_and_invalidated(api_client, book):
    assert api_client.get('/api/books/').data['results'][0]['title'] == 'Кобзар'
    Book.objects.filter(pk=book.pk).update(title='Без сигналу')
    assert api_client.get('/api/books/').data['results'][0]['title'] == 'Кобзар'
    BookFactory(title='Енеїда')
    titles = [item['title'] for item in api_client.get('/api/books/').json()['results']]
    assert titles == ['Без сигналу', 'Енеїда']


def test_api_category_list_is_invalidated_on_category_change(api_client, category):
    api_client.get('/api/categories/')
    CategoryFactory(name='Драма')
    names = [item['name'] for item in api_client.get('/api/categories/').json()['results']]
    assert names == ['Драма', 'Класика']


def test_api_list_cache_is_shared_between_anonymous_and_authenticated(api_client, user, book):
    authenticated_client = APIClient()
    authenticated_client.force_authenticate(user)
    anonymous = api_client.get('/api/books/').json()
    authenticated = authenticated_client.get('/api/books/').json()
    assert anonymous == authenticated


def test_book_detail_fragment_is_cached_and_invalidated(client, book):
    url = reverse('books:detail', args=[book.pk])
    assert 'Кобзар' in client.get(url).content.decode()
    assert cache.get(make_template_fragment_key('book_detail', [book.pk, 'uk'])) is not None

    Book.objects.filter(pk=book.pk).update(author='Невідомий автор')
    assert 'Невідомий автор' not in client.get(url).content.decode()

    book.refresh_from_db()
    book.save()
    assert cache.get(make_template_fragment_key('book_detail', [book.pk, 'uk'])) is None
    assert 'Невідомий автор' in client.get(url).content.decode()


def test_book_detail_fragment_is_cached_per_language(client, book):
    client.get(reverse('books:detail', args=[book.pk]))
    content = client.get(f'/en/books/{book.pk}/').content.decode()
    assert 'Author' in content


def test_book_list_fragment_is_invalidated_on_new_book(client, book):
    url = reverse('books:list')
    client.get(url)
    BookFactory(title='Енеїда')
    assert 'Енеїда' in client.get(url).content.decode()


def test_catalog_stats_fragment_is_invalidated_on_category_change(client, category):
    url = reverse('books:stats')
    client.get(url)
    assert cache.get(make_template_fragment_key('catalog_categories', ['uk'])) is not None
    CategoryFactory(name='Драма')
    assert cache.get(make_template_fragment_key('catalog_categories', ['uk'])) is None
    assert 'Драма' in client.get(url).content.decode()


def test_category_page_fragment_is_invalidated_on_book_change(client, book):
    url = reverse('books:category', args=[book.category.slug])
    client.get(url)
    book.title = 'Кобзар (нове видання)'
    book.save()
    assert 'Кобзар (нове видання)' in client.get(url).content.decode()


def test_catalog_version_changes_on_book_save(book):
    version = get_catalog_version()
    book.save()
    assert get_catalog_version() != version


def test_catalog_version_is_created_when_missing():
    cache.clear()
    version = get_catalog_version()
    assert version == get_catalog_version()


def test_book_detail_cache_key_is_normalized(api_client, book):
    assert api_client.get(f'/api/books/0{book.pk}/').status_code == 200
    assert cache.get(book_detail_key(book.pk)) is not None
    book.title = 'Оновлено'
    book.save()
    assert api_client.get(f'/api/books/0{book.pk}/').data['title'] == 'Оновлено'


def test_book_detail_with_non_numeric_id_is_404(api_client, db):
    assert api_client.get('/api/books/abc/').status_code == 404


def test_browsable_api_of_session_user_is_not_served_to_anonymous(client, category):
    client.force_login(UserFactory(username='secretadmin', is_staff=True))
    assert 'secretadmin' in client.get('/api/categories/', HTTP_ACCEPT='text/html').content.decode()
    anonymous = APIClient().get('/api/categories/', HTTP_ACCEPT='text/html').content.decode()
    assert 'secretadmin' not in anonymous


def test_browsable_api_of_jwt_user_is_not_served_to_anonymous(category):
    jwt_client = APIClient()
    jwt_client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(UserFactory(username="jwtadmin")).access_token}')
    assert 'jwtadmin' in jwt_client.get('/api/categories/', HTTP_ACCEPT='text/html').content.decode()
    assert 'jwtadmin' not in APIClient().get('/api/categories/', HTTP_ACCEPT='text/html').content.decode()


def test_api_list_cache_varies_on_accept(api_client, category):
    assert api_client.get('/api/categories/', HTTP_ACCEPT='text/html')['Content-Type'].startswith('text/html')
    assert api_client.get('/api/categories/', HTTP_ACCEPT='application/json')['Content-Type'] == 'application/json'
