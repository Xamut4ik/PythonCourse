from django.contrib.auth.models import AbstractUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import models



class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=40)

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=100)
    author = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    stock = models.IntegerField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    # class Meta:
    #     permissions = [
    #         ("publish_book", "Can publish book"),
    #     ]


class CustomUser(AbstractUser):
    email = models.EmailField(max_length=100, unique=True)

