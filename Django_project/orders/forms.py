from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Order


class CartAddBookForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=20,
        initial=1,
        label=_('Quantity'),
        help_text=_('From 1 to 20 copies.'),
        error_messages={
            'min_value': _('Quantity must be at least 1.'),
            'max_value': _('You can order at most 20 copies at once.'),
        },
    )
    override = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput)


class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['first_name', 'last_name', 'email', 'address', 'city']
        help_texts = {
            'email': _('We will send the order confirmation to this address.'),
            'address': _('Street, building and apartment.'),
        }
        error_messages = {
            'email': {'invalid': _('Enter a valid email address.')},
        }
