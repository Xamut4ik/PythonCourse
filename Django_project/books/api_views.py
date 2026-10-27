from django.db.models import Count, ProtectedError
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.response import Response

from api.permissions import IsAdminOrReadOnly
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
            'Пагінований список книг з вкладеною категорією. Фільтри: `category`, `category_slug`, '
            '`author`, `min_price`, `max_price`, `in_stock`. Пошук `search` за назвою, автором та описом. '
            'Сортування `ordering`: `title`, `price`, `stock` (з `-` для спадання). Доступно всім.'
        ),
    ),
    retrieve=extend_schema(summary='Книга', description='Дані однієї книги з вкладеною категорією. Доступно всім.'),
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


@extend_schema_view(
    list=extend_schema(
        summary='Список категорій',
        description='Категорії з кількістю книг `books_count`. Пошук `search` за назвою. Доступно всім.',
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
