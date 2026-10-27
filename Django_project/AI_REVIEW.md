# AI Code Review

Проєкт побудований на Django class-based views без Django REST Framework, тому серіалізаторів немає. Для review вибрано три найскладніші views: пошук і пагінація каталогу, додавання в кошик з перевіркою залишку та обробка повернення зі Stripe.

Після змін: `pytest` — 144 passed, наявна поведінка та URL не змінені.

---

## 1. `books/views.py` — `ListBooks` (та пов'язаний `DetailBook`)

### Оригінальний код

```python
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
```

### Рекомендації AI

| # | Категорія | Рекомендація |
|---|-----------|--------------|
| 1 | Читабельність | Замінити об'єднання двох QuerySet через `\|` на один `filter(Q(...) \| Q(...))`: це явніше показує намір і не залежить від того, як ORM поєднує два запити. |
| 2 | Валідація | Обрізати пробіли в `q`: запит `"  Кобзар "` зараз нічого не знаходить, а рядок з одних пробілів запускає фільтр `icontains ' '`. |
| 3 | Читабельність | Параметр `q` читається у двох місцях (`get_queryset`, `get_context_data`) — винести в один метод. |
| 4 | Коректність | `order_by('title')` неоднозначний для книг з однаковою назвою: при пагінації одна книга може з'явитися на двох сторінках або зникнути. Додати `pk` як другий ключ. |
| 5 | Продуктивність | У `book_detail.html` використовується `book.category` — це окремий SQL-запит. Додати `select_related('category')` у `DetailBook`. |
| 6 | Продуктивність | Для великого каталогу додати `db_index` на `title`/`author` або повнотекстовий пошук. |
| 7 | Логування | f-string у `logger.info` у `CreateBook` форматується завжди, навіть якщо рівень INFO вимкнено — використовувати `%s`-аргументи. |
| 8 | Безпека | Обмежити довжину `q`. |

### Що застосовано

- **1, 2, 3, 4, 5, 7** — застосовано.

### Що не застосовано і чому

- **6** — потребує нової міграції та зміни схеми БД; для поточного обсягу каталогу ефекту немає, а `icontains` з `%...%` все одно не використовує звичайний B-tree індекс.
- **8** — довжину рядка запиту вже обмежує вебсервер (у Gunicorn `limit_request_line` за замовчуванням 4094 байти), а значення передається в ORM параметризовано, тож SQL-ін'єкції немає. Додаткове обмеження змінило б поведінку пошуку без реальної користі.

### Фінальний код

```python
class ListBooks(ListView):
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 6

    def get_search_query(self):
        return self.request.GET.get('q', '').strip()

    def get_queryset(self):
        logger.info("Відкрито список книг")
        queryset = Book.objects.order_by('title', 'pk')
        query = self.get_search_query()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(author__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.get_search_query()
        return context


class DetailBook(DetailView):
    model = Book
    template_name = 'books/book_detail.html'
    context_object_name = 'book'

    def get_queryset(self):
        return Book.objects.select_related('category')
```

(docstrings опущено для стислості; повна версія — у файлі.)

---

## 2. `orders/views.py` — `CartAdd`

### Оригінальний код

```python
class CartAdd(View):
    def post(self, request, book_id):
        book = get_object_or_404(Book, pk=book_id)
        cart = Cart(request)
        form = CartAddBookForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Invalid quantity.'))
            return redirect('orders:cart_detail')

        quantity = form.cleaned_data['quantity']
        override = form.cleaned_data['override']
        in_cart = cart.cart.get(str(book.id), {}).get('quantity', 0)
        wanted = quantity if override else in_cart + quantity
        if wanted > book.stock:
            messages.error(request, _('Only %(stock)s copies of "%(title)s" are in stock.') % {
                'stock': book.stock, 'title': book.title,
            })
        else:
            cart.add(book, quantity=quantity, override_quantity=override)
            messages.success(request, _('"%(title)s" added to the cart.') % {'title': book.title})
        return redirect('orders:cart_detail')
```

### Рекомендації AI

| # | Категорія | Рекомендація |
|---|-----------|--------------|
| 1 | Інкапсуляція | View звертається до внутрішнього словника `cart.cart` і знає формат ключів (`str(book.id)`). Додати метод `Cart.get_quantity(book)`. |
| 2 | Читабельність | Замінити `if/else` на ранній `return` після помилки — так само, як для невалідної форми. |
| 3 | Читабельність | Створювати `Cart` після перевірки форми, коли він справді потрібен. |
| 4 | Безпека / конкурентність | Перевірка залишку не атомарна: між додаванням у кошик і оформленням інший покупець може купити книгу. |
| 5 | Безпека | Обмежити HTTP-методи декоратором `require_POST`. |
| 6 | Продуктивність | `get_object_or_404` викликається до валідації форми — для невалідної форми це зайвий запит. |

### Що застосовано

- **1, 2, 3** — застосовано, додано `Cart.get_quantity()` в `orders/cart.py`.

### Що не застосовано і чому

- **4** — кошик лише резервує намір, а не товар. Остаточна атомарна перевірка вже є в `services.create_order_from_cart` (`select_for_update` + перевірка `stock` у транзакції), тож блокування на етапі кошика зайве.
- **5** — `View` вже повертає 405 для будь-якого методу, крім визначеного `post`; декоратор нічого б не додав.
- **6** — перенесення змінило б поведінку: зараз для неіснуючої книги завжди повертається 404 незалежно від даних форми (це зафіксовано тестом). Один запит за PK не вартий зміни API.

### Фінальний код

```python
class CartAdd(View):
    def post(self, request, book_id):
        book = get_object_or_404(Book, pk=book_id)
        form = CartAddBookForm(request.POST)
        if not form.is_valid():
            messages.error(request, _('Invalid quantity.'))
            return redirect('orders:cart_detail')

        cart = Cart(request)
        quantity = form.cleaned_data['quantity']
        override = form.cleaned_data['override']
        wanted = quantity if override else cart.get_quantity(book) + quantity
        if wanted > book.stock:
            messages.error(request, _('Only %(stock)s copies of "%(title)s" are in stock.') % {
                'stock': book.stock, 'title': book.title,
            })
            return redirect('orders:cart_detail')

        cart.add(book, quantity=quantity, override_quantity=override)
        messages.success(request, _('"%(title)s" added to the cart.') % {'title': book.title})
        return redirect('orders:cart_detail')
```

```python
# orders/cart.py
def get_quantity(self, book):
    return self.cart.get(str(book.id), {}).get('quantity', 0)
```

---

## 3. `orders/views.py` — `PaymentSuccess`

### Оригінальний код

```python
class PaymentSuccess(TemplateView):
    template_name = 'orders/payment_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = self.request.GET.get('session_id')
        if not session_id:
            raise Http404
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            raise Http404
        mark_order_paid(session)
        context['order'] = get_own_order(self.request, int(session.client_reference_id))
        return context
```

### Рекомендації AI

| # | Категорія | Рекомендація |
|---|-----------|--------------|
| 1 | Помилка | `int(session.client_reference_id)` падає з `TypeError`/`ValueError` (HTTP 500), якщо сесія Stripe створена без `client_reference_id` або з нечисловим значенням (наприклад, з Dashboard чи іншого інтеграційного коду). Треба повертати 404 і не викликати `mark_order_paid`. |
| 2 | Безпека | `mark_order_paid` викликається до перевірки, що замовлення належить поточному відвідувачу. Перенести перевірку власника вище. |
| 3 | Best practice | `stripe.api_key = ...` змінює глобальний стан модуля на кожному запиті. Передавати ключ через `retrieve(session_id, api_key=...)` або `StripeClient`. |
| 4 | Архітектура | Побічна дія (зміна статусу замовлення) у `get_context_data` GET-запиту. Перенести логіку в `get()` або покладатися лише на webhook. |
| 5 | Продуктивність | Замовлення читається двічі: у `mark_order_paid` і в `get_own_order`. |

### Що застосовано

- **1** — застосовано: нечисловий або порожній `client_reference_id` тепер дає 404, а замовлення не змінюється. Додано тест `test_payment_success_with_bad_client_reference_is_404`.

### Що не застосовано і чому

- **2** — сесію отримано напряму з API Stripe з секретним ключем, і `mark_order_paid` змінює статус тільки при `payment_status == 'paid'`. Тобто позначається оплаченим лише справді оплачене замовлення — так само це робить webhook без жодної сесії користувача. Чужі дані не розкриваються: `get_own_order` все одно поверне 404. Перенесення перевірки змінило б поведінку (оплата з іншого браузера не фіксувалась би до приходу webhook).
- **3** — `services.create_checkout_session` використовує той самий підхід із глобальним ключем; ключ один на весь застосунок, тож гонки немає. Міняти тільки одне місце — непослідовно, а міграція на `StripeClient` виходить за межі цього review.
- **4** — повернення зі Stripe завжди приходить GET-запитом, тому зробити цей крок POST не можна; синхронна фіксація оплати потрібна, щоб користувач одразу бачив статус «Оплачено», навіть якщо webhook затримується. Операція ідемпотентна (`if not order.is_paid`).
- **5** — `mark_order_paid` — сервіс, спільний з webhook, і він бере `select_for_update` у власній транзакції. Передавати в нього об'єкт ззовні означало б змінити його контракт заради одного запиту за PK.

### Фінальний код

```python
class PaymentSuccess(TemplateView):
    template_name = 'orders/payment_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = self.request.GET.get('session_id')
        if not session_id:
            raise Http404
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            raise Http404
        try:
            order_id = int(session.client_reference_id)
        except (TypeError, ValueError):
            raise Http404
        mark_order_paid(session)
        context['order'] = get_own_order(self.request, order_id)
        return context
```
