from decimal import Decimal

from django.conf import settings

from books.models import Book


class Cart:
    """Кошик, що зберігається в сесії: {book_id: {'quantity': int, 'price': str}}."""

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if cart is None:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, book, quantity=1, override_quantity=False):
        book_id = str(book.id)
        if book_id not in self.cart:
            self.cart[book_id] = {'quantity': 0, 'price': str(book.price)}
        if override_quantity:
            self.cart[book_id]['quantity'] = quantity
        else:
            self.cart[book_id]['quantity'] += quantity
        self.save()

    def remove(self, book):
        book_id = str(book.id)
        if book_id in self.cart:
            del self.cart[book_id]
            self.save()

    def clear(self):
        del self.session[settings.CART_SESSION_ID]
        self.cart = self.session[settings.CART_SESSION_ID] = {}
        self.save()

    def save(self):
        # Сесія не бачить змін вкладених словників, тому позначаємо її вручну
        self.session.modified = True

    def __iter__(self):
        books = Book.objects.filter(id__in=self.cart.keys())
        cart = {book_id: dict(item) for book_id, item in self.cart.items()}
        for book in books:
            cart[str(book.id)]['book'] = book
        for item in cart.values():
            if 'book' not in item:
                # Книгу видалили з каталогу після додавання в кошик
                continue
            item['price'] = Decimal(item['price'])
            item['total_price'] = item['price'] * item['quantity']
            yield item

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def get_total_price(self):
        return sum(
            (Decimal(item['price']) * item['quantity'] for item in self.cart.values()),
            Decimal('0'),
        )
