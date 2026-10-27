from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Book, Category


class CategorySerializer(serializers.ModelSerializer):
    books_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'books_count']

    def get_books_count(self, obj) -> int:
        count = getattr(obj, 'books_count', None)
        return obj.book_set.count() if count is None else count

    def validate_slug(self, value):
        queryset = Category.objects.filter(slug=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(_('A category with this slug already exists.'))
        return value


class CategoryShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class BookSerializer(serializers.ModelSerializer):
    category = CategoryShortSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source='category', queryset=Category.objects.all(), write_only=True,
    )
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Book
        fields = ['id', 'title', 'author', 'description', 'price', 'stock', 'in_stock', 'category', 'category_id']

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError(_('Price cannot be negative.'))
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError(_('Stock cannot be negative.'))
        return value


class BookShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ['id', 'title', 'author', 'price']
