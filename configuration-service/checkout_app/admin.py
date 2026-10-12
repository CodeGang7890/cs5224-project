from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import OrderItem, ScheduleItem


class ChatSessionLinkMixin:
    """A "Chat session" column / read-only field: the chat's ID, linking to its admin page."""

    @admin.display(description='Chat session', ordering='chat_session')
    def chat_session_link(self, obj):
        if obj.chat_session_id is None:
            return '—'
        url = reverse('admin:chat_app_chatsession_change', args=[obj.chat_session_id])
        return format_html('<a href="{}">#{}</a>', url, obj.chat_session_id)


@admin.register(OrderItem)
class OrderItemAdmin(ChatSessionLinkMixin, admin.ModelAdmin):
    list_display = (
        'id', 'business', 'order_status', 'payment_reference', 'is_sandbox', 'chat_session_link', 'created_time',
    )
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name', 'payment_reference')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    raw_id_fields = ('chat_session',)
    readonly_fields = ('payment_reference', 'chat_session_link', 'created_time', 'updated_time')


@admin.register(ScheduleItem)
class ScheduleItemAdmin(ChatSessionLinkMixin, admin.ModelAdmin):
    list_display = (
        'id', 'business', 'service', 'service_provider', 'start_time', 'order_status', 'payment_reference',
        'is_sandbox', 'chat_session_link',
    )
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name', 'service__name', 'service_provider__name', 'payment_reference')
    list_select_related = ('business', 'service', 'service_provider')
    autocomplete_fields = ('business', 'service', 'service_provider')
    raw_id_fields = ('chat_session',)
    readonly_fields = ('payment_reference', 'chat_session_link', 'created_time', 'updated_time')
