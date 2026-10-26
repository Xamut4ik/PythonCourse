from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    raw_id_fields = ('book',)
    readonly_fields = ('cost',)
    extra = 0

    @admin.display(description=_('Cost'))
    def cost(self, obj):
        return obj.get_cost() if obj.pk else '-'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'email', 'city', 'status', 'total', 'created')
    list_filter = ('status', 'created')
    search_fields = ('id', 'first_name', 'last_name', 'email')
    readonly_fields = ('stripe_session_id', 'stripe_payment_intent', 'created', 'updated')
    inlines = [OrderItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    @admin.display(description=_('Total'))
    def total(self, obj):
        return obj.get_total_cost()
