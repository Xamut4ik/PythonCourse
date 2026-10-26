from asgiref.sync import sync_to_async
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import aget_object_or_404, render

from .models import Book, Category

arender = sync_to_async(render)


async def catalog_stats(request):
    totals = await Book.objects.aaggregate(total_stock=Sum('stock'))
    context = {
        'books_count': await Book.objects.acount(),
        'categories_count': await Category.objects.acount(),
        'out_of_stock_count': await Book.objects.filter(stock__lte=0).acount(),
        'total_stock': totals['total_stock'] or 0,
        'categories': [
            category
            async for category in Category.objects.annotate(book_count=Count('book')).order_by('name')
        ],
    }
    return await arender(request, 'books/catalog_stats.html', context)


async def category_books(request, slug):
    category = await aget_object_or_404(Category, slug=slug)
    books = [book async for book in Book.objects.filter(category=category).order_by('title')]
    return await arender(request, 'books/category_books.html', {'category': category, 'books': books})


async def book_api(request, pk):
    book = await Book.objects.select_related('category').filter(pk=pk).afirst()
    if book is None:
        return JsonResponse({'error': 'not found'}, status=404)
    return JsonResponse({
        'id': book.pk,
        'title': book.title,
        'author': book.author,
        'price': str(book.price),
        'stock': book.stock,
        'in_stock': book.in_stock,
        'category': book.category.name,
    })
