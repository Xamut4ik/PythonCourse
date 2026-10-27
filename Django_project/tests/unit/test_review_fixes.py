import pytest
import stripe
from django.urls import reverse

from tests.factories import BookFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_book_search_ignores_surrounding_spaces(client, book, book2):
    # Generated with AI, reviewed and modified
    response = client.get(reverse('books:list'), {'q': '  Кобз  '})
    assert list(response.context['books']) == [book]
    assert response.context['query'] == 'Кобз'


def test_book_search_matches_author(client, book, book2):
    # Generated with AI, reviewed and modified
    response = client.get(reverse('books:list'), {'q': 'Коцюб'})
    assert list(response.context['books']) == [book2]


def test_book_detail_loads_category_in_one_query(client, book, django_assert_max_num_queries):
    # Generated with AI, reviewed and modified
    client.get(reverse('books:list'))
    with django_assert_max_num_queries(3):
        response = client.get(reverse('books:detail', args=[book.pk]))
    assert response.status_code == 200


def test_cart_add_respects_quantity_already_in_cart(client, add_to_cart, cart_session):
    # Generated with AI, reviewed and modified
    book = BookFactory(stock=3)
    add_to_cart(book, 2)
    add_to_cart(book, 2)
    assert cart_session()[str(book.pk)]['quantity'] == 2


def test_cart_add_invalid_form_for_missing_book_is_404(client):
    # Generated with AI, reviewed and modified
    response = client.post(reverse('orders:cart_add', args=[999]), {'quantity': 0})
    assert response.status_code == 404


@pytest.mark.parametrize('reference', [None, '', 'abc'])
def test_payment_success_with_bad_client_reference_is_404(client, mocker, reference):
    # Generated with AI, reviewed and modified
    session = stripe.checkout.Session.construct_from(
        {'id': 'cs_test_1', 'payment_status': 'paid', 'client_reference_id': reference}, 'sk_test_dummy',
    )
    mocker.patch('stripe.checkout.Session.retrieve', return_value=session)
    mark_paid = mocker.patch('orders.views.mark_order_paid')
    response = client.get(reverse('orders:payment_success'), {'session_id': 'cs_test_1'})
    assert response.status_code == 404
    mark_paid.assert_not_called()
