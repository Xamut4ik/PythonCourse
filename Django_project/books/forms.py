from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import Book, CustomUser


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')
        labels = {'email': _('Email')}
        help_texts = {'email': _('Used for order confirmations.')}
        error_messages = {
            'email': {'unique': _('A user with this email already exists.')},
        }


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ['title', 'author', 'category', 'price', 'stock', 'description']
        error_messages = {
            'price': {'invalid': _('Enter a valid price.')},
        }

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError(_('Price must be greater than zero.'))
        return price

    def clean_stock(self):
        stock = self.cleaned_data['stock']
        if stock < 0:
            raise forms.ValidationError(_('Stock cannot be negative.'))
        return stock
