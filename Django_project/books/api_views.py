from django.core.cache import cache
from django.db.models import Count, ProtectedError
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.response import Response

from api.permissions import IsAdminOrReadOnly
from .cache import BOOK_DETAIL_TIMEOUT, LIST_TIMEOUT, LIST_VARY_HEADERS, PAGES_CACHE, book_detail_key
from .filters import BookFilter
from .models import Book, Category
from .serializers import BookSerializer, CategorySerializer


class ProtectedDestroyMixin:
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'detail': _('The object cannot be deleted because its books are used in orders.')},
                status=status.HTTP_409_CONFLICT,
            )

@extend_schema_view(
    list=extend_schema(
        summary='Список книг',
        description=(
            'Пагінований список книг з вкладеною категорією, кешується на 5 хвилин. Фільтри: `category`, `category_slug`, '
            '`author`, `min_price`, `max_price`, `in_stock`. Пошук `search` за назвою, автором та описом. '
            'Сортування `ordering`: `title`, `price`, `stock` (з `-` для спадання). Доступно всім.'
        ),
    ),
    retrieve=extend_schema(
        summary='Книга',
        description='Дані однієї книги з вкладеною категорією, кешуються на 15 хвилин. Доступно всім.',
    ),
    create=extend_schema(
        summary='Створити книгу',
        description='Категорія передається через `category_id`. Ціна і залишок не можуть бути від\'ємними. Тільки адміністратор.',
    ),
    update=extend_schema(summary='Оновити книгу', description='Повне оновлення книги. Тільки адміністратор.'),
    partial_update=extend_schema(summary='Частково оновити книгу', description='Тільки адміністратор.'),
    destroy=extend_schema(
        summary='Видалити книгу',
        description='Книгу, яка є в замовленнях, видалити не можна (409). Тільки адміністратор.',
    ),
)
class BookViewSet(ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = Book.objects.select_related('category').order_by('title', 'pk')
    serializer_class = BookSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = BookFilter
    search_fields = ['title', 'author', 'description']
    ordering_fields = ['title', 'price', 'stock']

    @method_decorator(cache_page(LIST_TIMEOUT, cache=PAGES_CACHE))
    @method_decorator(vary_on_headers(*LIST_VARY_HEADERS))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        try:
            book_id = int(kwargs[self.lookup_url_kwarg or self.lookup_field])
        except ValueError:
            return super().retrieve(request, *args, **kwargs)
        key = book_detail_key(book_id)
        data = cache.get(key)
        if data is None:
            data = dict(self.get_serializer(self.get_object()).data)
            cache.set(key, data, BOOK_DETAIL_TIMEOUT)
        return Response(data)


@extend_schema_view(
    list=extend_schema(
        summary='Список категорій',
        description='Категорії з кількістю книг `books_count`, кешуються на 5 хвилин. Пошук `search` за назвою. Доступно всім.',
    ),
    retrieve=extend_schema(summary='Категорія', description='Дані однієї категорії. Доступно всім.'),
    create=extend_schema(summary='Створити категорію', description='Slug має бути унікальним. Тільки адміністратор.'),
    update=extend_schema(summary='Оновити категорію', description='Тільки адміністратор.'),
    partial_update=extend_schema(summary='Частково оновити категорію', description='Тільки адміністратор.'),
    destroy=extend_schema(
        summary='Видалити категорію',
        description=(
            'Видаляє категорію разом з усіма її книгами. Якщо якась книга є в замовленнях, '
            'повертає 409. Тільки адміністратор.'
        ),
    ),
)
class CategoryViewSet(ProtectedDestroyMixin, viewsets.ModelViewSet):
    queryset = Category.objects.annotate(books_count=Count('book')).order_by('name', 'pk')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['name']
    ordering_fields = ['name', 'books_count']
    filterset_fields = ['slug']

    @method_decorator(cache_page(LIST_TIMEOUT, cache=PAGES_CACHE))
    @method_decorator(vary_on_headers(*LIST_VARY_HEADERS))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
