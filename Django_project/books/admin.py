from django.contrib import admin
from .models import Category, Book


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'price', 'stock')
    list_filter = ('author', 'category')
    search_fields = ('title', 'author')


class BookInline(admin.TabularInline):
    model = Book

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    inlines = [BookInline]