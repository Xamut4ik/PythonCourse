from django.urls import path
from . import views

app_name = 'books'

urlpatterns = [
    path('', views.ListBooks.as_view(), name='list'),
    path('create/', views.CreateBook.as_view(), name='create'),
    path('<int:pk>/', views.DetailBook.as_view(), name='detail'),
    path('<int:pk>/update/', views.UpdateBook.as_view(), name='update'),
    path('<int:pk>/delete/', views.DeleteBook.as_view(), name='delete'),
]