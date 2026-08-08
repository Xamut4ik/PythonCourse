from .models import Book, Category
from django.db.models import Q, Count


price_books = Book.objects.filter(price__lt=250)
ct_books = Book.objects.filter(Q(price__gt=250) | Q(stock__gt=5))
categort_annot = Category.objects.annotate(book_count=Count('book'))