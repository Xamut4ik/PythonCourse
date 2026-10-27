import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .forms import BookForm, CustomUserCreationForm
from .models import Book

logger = logging.getLogger(__name__)


class ListBooks(ListView):
    """Список книг з пошуком і пагінацією (по 6 на сторінку).

    GET-параметри:
        q: рядок пошуку за назвою або автором (без урахування регістру).
        page: номер сторінки.

    Повертає HTML-сторінку ``books/book_list.html`` з ``books``, ``page_obj`` і ``query``.
    Права доступу: доступно всім, включно з анонімними користувачами.
    """

    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 6

    def get_search_query(self):
        """Повертає рядок пошуку з параметра ``q`` без пробілів по краях."""
        return self.request.GET.get('q', '').strip()

    def get_queryset(self):
        """Повертає книги, відсортовані за назвою і відфільтровані за ``q``, якщо він заданий."""
        logger.info("Відкрито список книг")
        queryset = Book.objects.order_by('title', 'pk')
        query = self.get_search_query()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(author__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        """Додає до контексту поточний рядок пошуку ``query`` для форми."""
        context = super().get_context_data(**kwargs)
        context['query'] = self.get_search_query()
        return context


class DetailBook(DetailView):
    """Сторінка однієї книги.

    Параметри URL:
        pk: первинний ключ книги.

    Повертає HTML-сторінку ``books/book_detail.html`` з ``book`` або 404, якщо книги немає.
    Права доступу: доступно всім.
    """

    model = Book
    template_name = 'books/book_detail.html'
    context_object_name = 'book'

    def get_queryset(self):
        """Повертає книги разом із категорією одним запитом."""
        return Book.objects.select_related('category')


class BookPermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Спільна база для views, що змінюють каталог.

    Анонімного користувача перенаправляє на сторінку входу, автентифікованому
    без потрібного ``permission_required`` повертає 403. Після успішної дії
    перенаправляє на список книг.
    """

    login_url = reverse_lazy('books:login')
    success_url = reverse_lazy('books:list')


class CreateBook(BookPermissionMixin, CreateView):
    """Створення книги через ``BookForm``.

    GET показує порожню форму, POST зберігає книгу і перенаправляє на список.
    Повертає HTML-сторінку ``books/book_create.html`` або redirect.
    Права доступу: автентифікований користувач з правом ``books.add_book``.
    """

    model = Book
    form_class = BookForm
    template_name = 'books/book_create.html'
    permission_required = 'books.add_book'

    def form_valid(self, form):
        """Зберігає книгу, додає flash-повідомлення і повертає redirect на ``success_url``."""
        response = super().form_valid(form)
        messages.success(self.request, _('Book "%(title)s" created.') % {'title': self.object.title})
        logger.info("Книга %s створена", self.object)
        return response


class UpdateBook(BookPermissionMixin, UpdateView):
    """Редагування книги.

    Параметри URL:
        pk: первинний ключ книги.

    Повертає HTML-сторінку ``books/book_update.html``, redirect після збереження або 404.
    Права доступу: автентифікований користувач з правом ``books.change_book``.
    """

    model = Book
    form_class = BookForm
    template_name = 'books/book_update.html'
    context_object_name = 'book'
    permission_required = 'books.change_book'

    def form_valid(self, form):
        """Додає flash-повідомлення, зберігає зміни і повертає redirect на ``success_url``."""
        messages.success(self.request, _('Book "%(title)s" updated.') % {'title': form.instance.title})
        return super().form_valid(form)


class DeleteBook(BookPermissionMixin, DeleteView):
    """Видалення книги з підтвердженням.

    Параметри URL:
        pk: первинний ключ книги.

    GET показує сторінку підтвердження ``books/book_delete.html``, POST видаляє книгу
    і перенаправляє на список. Повертає 404, якщо книги немає.
    Права доступу: автентифікований користувач з правом ``books.delete_book``.
    """

    model = Book
    template_name = 'books/book_delete.html'
    context_object_name = 'book'
    permission_required = 'books.delete_book'

    def form_valid(self, form):
        """Додає flash-повідомлення, видаляє книгу і повертає redirect на ``success_url``."""
        messages.success(self.request, _('Book "%(title)s" deleted.') % {'title': self.object.title})
        return super().form_valid(form)


class RegisterUser(CreateView):
    """Реєстрація нового користувача через ``CustomUserCreationForm``.

    Повертає HTML-сторінку ``registration/register.html`` або redirect на сторінку входу.
    Права доступу: доступно всім.
    """

    form_class = CustomUserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('books:login')

    def form_valid(self, form):
        """Створює користувача, додає flash-повідомлення і повертає redirect на вхід."""
        messages.success(self.request, _('Registration successful. You can now log in.'))
        return super().form_valid(form)


class LoginUser(LoginView):
    """Вхід користувача.

    Повертає HTML-сторінку ``registration/login.html`` або redirect на ``next``
    чи на список книг. Права доступу: доступно всім.
    """

    template_name = 'registration/login.html'
    next_page = reverse_lazy('books:list')


class LogoutUser(LogoutView):
    """Вихід користувача (тільки POST).

    Повертає redirect на список книг. Права доступу: доступно всім.
    """

    next_page = reverse_lazy('books:list')
