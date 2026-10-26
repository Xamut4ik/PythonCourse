import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .forms import BookForm, CustomUserCreationForm
from .models import Book

logger = logging.getLogger(__name__)


class ListBooks(ListView):
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 6

    def get_queryset(self):
        logger.info("Відкрито список книг")
        queryset = Book.objects.order_by('title')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(title__icontains=query) | queryset.filter(author__icontains=query)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class DetailBook(DetailView):
    model = Book
    template_name = 'books/book_detail.html'
    context_object_name = 'book'


# Міксини мають стояти ліворуч від generic view, інакше їхній dispatch() не викликається
class BookPermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    login_url = reverse_lazy('books:login')
    success_url = reverse_lazy('books:list')


class CreateBook(BookPermissionMixin, CreateView):
    model = Book
    form_class = BookForm
    template_name = 'books/book_create.html'
    permission_required = 'books.add_book'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _('Book "%(title)s" created.') % {'title': self.object.title})
        logger.info(f"Книга {self.object} створена")
        return response


class UpdateBook(BookPermissionMixin, UpdateView):
    model = Book
    form_class = BookForm
    template_name = 'books/book_update.html'
    context_object_name = 'book'
    permission_required = 'books.change_book'

    def form_valid(self, form):
        messages.success(self.request, _('Book "%(title)s" updated.') % {'title': form.instance.title})
        return super().form_valid(form)


class DeleteBook(BookPermissionMixin, DeleteView):
    model = Book
    template_name = 'books/book_delete.html'
    context_object_name = 'book'
    permission_required = 'books.delete_book'

    def form_valid(self, form):
        messages.success(self.request, _('Book "%(title)s" deleted.') % {'title': self.object.title})
        return super().form_valid(form)


class RegisterUser(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('books:login')

    def form_valid(self, form):
        messages.success(self.request, _('Registration successful. You can now log in.'))
        return super().form_valid(form)


class LoginUser(LoginView):
    template_name = 'registration/login.html'
    next_page = reverse_lazy('books:list')


class LogoutUser(LogoutView):
    next_page = reverse_lazy('books:list')
