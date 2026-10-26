from django.http import Http404, JsonResponse

from .models import Order
from .views import SESSION_ORDER_IDS


async def order_status(request, pk):
    """JSON зі статусом замовлення — лише для власника (за сесією або обліковим записом)."""
    try:
        order = await Order.objects.aget(pk=pk)
    except Order.DoesNotExist:
        raise Http404
    user = await request.auser()
    own_by_session = pk in await request.session.aget(SESSION_ORDER_IDS, [])
    own_by_user = user.is_authenticated and order.user_id == user.id
    if not (own_by_session or own_by_user):
        raise Http404

    items = [item async for item in order.items.select_related('book')]
    return JsonResponse({
        'id': order.pk,
        'status': order.status,
        'status_display': order.get_status_display(),
        'is_paid': order.is_paid,
        'total': str(sum((item.get_cost() for item in items), 0)),
        'items': [
            {'title': item.book.title, 'quantity': item.quantity, 'price': str(item.price)}
            for item in items
        ],
    })
