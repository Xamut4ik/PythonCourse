import django_filters

from .models import Order


class OrderFilter(django_filters.FilterSet):
    created_after = django_filters.DateFilter(field_name='created', lookup_expr='date__gte')
    created_before = django_filters.DateFilter(field_name='created', lookup_expr='date__lte')

    class Meta:
        model = Order
        fields = ['status', 'created_after', 'created_before']
