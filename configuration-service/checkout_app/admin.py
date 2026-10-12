from django.contrib import admin

from .models import OrderItem, ScheduleItem


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'order_status', 'payment_reference', 'is_sandbox', 'chat_session', 'created_time')
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name', 'payment_reference')
    list_select_related = ('business', 'chat_session')
    autocomplete_fields = ('business',)
    raw_id_fields = ('chat_session',)
    readonly_fields = ('payment_reference', 'created_time', 'updated_time')


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'service', 'service_provider', 'start_time', 'order_status', 'payment_reference', 'is_sandbox')
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name', 'service__name', 'service_provider__name', 'payment_reference')
    list_select_related = ('business', 'service', 'service_provider')
    autocomplete_fields = ('business', 'service', 'service_provider')
    raw_id_fields = ('chat_session',)
    readonly_fields = ('payment_reference', 'created_time', 'updated_time')
