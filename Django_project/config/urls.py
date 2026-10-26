from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from orders.views import StripeWebhook

# Без мовного префікса: перемикач мови, вебхук Stripe (йому потрібна стабільна адреса) і debug toolbar
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('payment/webhook/', StripeWebhook.as_view(), name='stripe_webhook'),
    path('__debug__/', include('debug_toolbar.urls')),
]

urlpatterns += i18n_patterns(
    path('', RedirectView.as_view(pattern_name='books:list'), name='home'),
    path('admin/', admin.site.urls),
    path('books/', include('books.urls')),
    path('', include('orders.urls')),
)
