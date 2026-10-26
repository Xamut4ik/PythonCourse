import pytest
from django.utils import translation

from books.forms import BookForm, CustomUserCreationForm
from orders.forms import CartAddBookForm, OrderCreateForm
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


def test_cart_add_form_valid():
    form = CartAddBookForm({'quantity': 3, 'override': 'True'})
    assert form.is_valid()
    assert form.cleaned_data == {'quantity': 3, 'override': True}


@pytest.mark.parametrize('quantity, message', [
    (0, 'Кількість має бути не менше 1.'),
    (21, 'За раз можна замовити не більше 20 примірників.'),
    ('abc', 'Введіть ціле число.'),
])
def test_cart_add_form_invalid(quantity, message):
    form = CartAddBookForm({'quantity': quantity})
    assert not form.is_valid()
    assert form.errors['quantity'] == [message]


def test_cart_add_form_errors_follow_active_language():
    with translation.override('en'):
        form = CartAddBookForm({'quantity': 0})
        assert form.errors['quantity'] == ['Quantity must be at least 1.']


def test_order_form_valid(order_data):
    assert OrderCreateForm(order_data).is_valid()


def test_order_form_invalid_email_and_missing_fields(order_data):
    order_data.update(email='not-an-email', city='')
    form = OrderCreateForm(order_data)
    assert not form.is_valid()
    assert form.errors['email'] == ['Введіть коректну email-адресу.']
    assert 'city' in form.errors


def test_order_form_labels_and_help_texts_are_translated():
    with translation.override('uk'):
        form = OrderCreateForm()
        assert form.fields['city'].label == 'Місто'
        assert form.fields['email'].help_text == 'На цю адресу ми надішлемо підтвердження замовлення.'


@pytest.mark.django_db
def test_registration_form_valid():
    form = CustomUserCreationForm({
        'username': 'newuser', 'email': 'new@example.com',
        'password1': 'Sup3r-secret!', 'password2': 'Sup3r-secret!',
    })
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_registration_form_rejects_duplicate_email_and_password_mismatch():
    UserFactory(email='taken@example.com')
    form = CustomUserCreationForm({
        'username': 'newuser', 'email': 'taken@example.com',
        'password1': 'Sup3r-secret!', 'password2': 'other-secret!',
    })
    assert not form.is_valid()
    assert form.errors['email'] == ['Користувач з таким email уже існує.']
    assert 'password2' in form.errors


@pytest.mark.django_db
def test_book_form_valid(category):
    form = BookForm({
        'title': 'Енеїда', 'author': 'Котляревський', 'category': category.pk,
        'price': '199.99', 'stock': 3, 'description': 'Поема',
    })
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_book_form_rejects_non_positive_price_and_negative_stock(category):
    form = BookForm({
        'title': 'Енеїда', 'author': 'Котляревський', 'category': category.pk,
        'price': '0', 'stock': -1, 'description': 'Поема',
    })
    assert not form.is_valid()
    assert form.errors['price'] == ['Ціна має бути більшою за нуль.']
    assert form.errors['stock'] == ['Кількість на складі не може бути відʼємною.']
