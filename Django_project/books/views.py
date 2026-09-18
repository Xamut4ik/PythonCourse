from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from .models import Book
from .forms import CustomUser, CustomUserCreationForm
import logging


# def book_list(request):
#     books = Book.objects.all()
#
#     return render(request, 'books/book_list.html', {'books': books})
#
# def book_detail(request, pk):
#     book = get_object_or_404(Book, pk=pk)
#
#     return render(request, 'books/book_detail.html', {'books': book})


class ListBooks(ListView):
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 6

    def get_queryset(self):
        logger.info("Відкрито список книг")
        queryset = Book.objects.all()
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(title__icontains=query) | queryset.filter(author__icontains=query)
        return queryset

class DetailBook(DetailView):
    model = Book
    template_name = 'books/book_detail.html'
    context_object_name = 'book'


class CreateBook(CreateView, LoginRequiredMixin, PermissionRequiredMixin):
    model = Book
    template_name = 'books/book_create.html'
    context_object_name = 'book'
    fields = '__all__'
    login_url = reverse_lazy('books:login')
    success_url = reverse_lazy('books:list')
    permission_required = 'books.add_book'
    permission_denied_message = "Для додавання нової книги увійдіть в акаунт."

    def form_valid(self, form):
        response = super().form_valid(form)

        logger.info(f"Книга {self.object} створена")
        return response


class UpdateBook(UpdateView):
    model = Book
    template_name = 'books/book_update.html'
    context_object_name = 'book'
    fields = '__all__'
    success_url = reverse_lazy('books:list')

class DeleteBook(DeleteView):
    model = Book
    template_name = 'books/book_delete.html'
    context_object_name = 'books'
    success_url = reverse_lazy('books:list')


class RegisterUser(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('books:login')

class LoginUser(LoginView):
    template_name = 'registration/login.html'
    next_page = reverse_lazy('books:list')


class LogoutUser(LogoutView):
    next_page = reverse_lazy('books:list')

logger = logging.getLogger(__name__)