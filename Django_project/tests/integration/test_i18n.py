import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_root_redirects_to_default_language(client):
    response = client.get('/', follow=True)
    assert response.redirect_chain[-1] == ('/uk/books/', 302)
    assert '<html lang="uk">' in response.content.decode()


def test_accept_language_header_picks_english(client):
    response = client.get('/', headers={'accept-language': 'en'})
    assert response.url == '/en/'


def test_language_switcher_changes_language(client, book):
    response = client.get(reverse('books:list'))
    assert 'Список книг' in response.content.decode()
    assert 'action="/i18n/setlang/"' in response.content.decode()

    response = client.post('/i18n/setlang/', {'language': 'en', 'next': '/uk/books/'}, follow=True)

    assert response.redirect_chain == [('/en/books/', 302)]
    content = response.content.decode()
    assert 'Book list' in content
    assert '<html lang="en">' in content
    assert client.cookies[settings.LANGUAGE_COOKIE_NAME].value == 'en'


def test_pages_are_translated(client, book, add_to_cart):
    add_to_cart(book, 2)
    uk = client.get('/uk/cart/').content.decode()
    en = client.get('/en/cart/').content.decode()
    assert 'Оформити замовлення' not in uk
    assert 'Оформлення замовлення' in uk and '501,00 грн' in uk
    assert 'Checkout' in en and '501.00 UAH' in en


def test_messages_and_form_errors_follow_url_language(client, book):
    response = client.post(f'/en/cart/add/{book.pk}/', {'quantity': 10}, follow=True)
    assert [str(m) for m in response.context['messages']] == ['Only 5 copies of "Кобзар" are in stock.']

    response = client.post(f'/en/cart/add/{book.pk}/', {'quantity': 99}, follow=True)
    assert [str(m) for m in response.context['messages']] == ['Invalid quantity.']

    response = client.post('/en/orders/create/', {})
    response = client.get(response.url)
    assert 'Your cart is empty.' in response.content.decode()


def test_reverse_uses_active_language():
    with translation.override('en'):
        assert reverse('books:list') == '/en/books/'
    assert reverse('books:list') == '/uk/books/'
