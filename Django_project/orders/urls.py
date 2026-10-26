from django.urls import path
from . import async_views, views

app_name = 'orders'

# Вебхук Stripe підключено в config/urls.py без мовного префікса
urlpatterns = [
    path('cart/', views.CartDetail.as_view(), name='cart_detail'),
    path('cart/add/<int:book_id>/', views.CartAdd.as_view(), name='cart_add'),
    path('cart/remove/<int:book_id>/', views.CartRemove.as_view(), name='cart_remove'),
    path('cart/clear/', views.CartClear.as_view(), name='cart_clear'),
    path('orders/create/', views.OrderCreate.as_view(), name='order_create'),
    path('orders/<int:pk>/pay/', views.OrderPay.as_view(), name='pay'),
    path('orders/<int:pk>/cancel/', views.PaymentCancel.as_view(), name='payment_cancel'),
    path('orders/<int:pk>/status/', async_views.order_status, name='order_status'),
    path('payment/success/', views.PaymentSuccess.as_view(), name='payment_success'),
]
