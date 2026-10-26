from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    name = models.CharField(_('name'), max_length=100)
    slug = models.SlugField(_('slug'), max_length=40)

    class Meta:
        verbose_name = _('category')
        verbose_name_plural = _('categories')

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(_('title'), max_length=100)
    author = models.CharField(_('author'), max_length=100)
    price = models.DecimalField(_('price'), max_digits=10, decimal_places=2)
    description = models.TextField(_('description'))
    stock = models.IntegerField(_('stock'), help_text=_('Number of copies in the warehouse.'))
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name=_('category'))

    class Meta:
        verbose_name = _('book')
        verbose_name_plural = _('books')

    def __str__(self):
        return self.title

    @property
    def in_stock(self):
        return self.stock > 0


class CustomUser(AbstractUser):
    email = models.EmailField(_('email address'), max_length=100, unique=True)

    class Meta(AbstractUser.Meta):
        verbose_name = _('user')
        verbose_name_plural = _('users')
