from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.CartDetail.as_view(), name='cart_detail'),
    path('cart/add/<int:book_id>/', views.CartAdd.as_view(), name='cart_add'),
    path('cart/remove/<int:book_id>/', views.CartRemove.as_view(), name='cart_remove'),
    path('cart/clear/', views.CartClear.as_view(), name='cart_clear'),
    path('orders/create/', views.OrderCreate.as_view(), name='order_create'),
    path('orders/<int:pk>/pay/', views.OrderPay.as_view(), name='pay'),
    path('orders/<int:pk>/cancel/', views.PaymentCancel.as_view(), name='payment_cancel'),
    path('payment/success/', views.PaymentSuccess.as_view(), name='payment_success'),
    path('payment/webhook/', views.StripeWebhook.as_view(), name='stripe_webhook'),
]
