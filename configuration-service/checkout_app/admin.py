from django.contrib import admin

from .models import OrderItem, ScheduleItem


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'order_status', 'is_sandbox', 'chat_session', 'created_time')
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name',)
    list_select_related = ('business', 'chat_session')
    autocomplete_fields = ('business',)
    raw_id_fields = ('chat_session',)
    readonly_fields = ('created_time', 'updated_time')


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'service', 'weekly_availability', 'start_time', 'order_status', 'is_sandbox')
    list_filter = ('order_status', 'is_sandbox', 'business')
    search_fields = ('business__business_name', 'service__name', 'weekly_availability__name')
    list_select_related = ('business', 'service', 'weekly_availability')
    autocomplete_fields = ('business', 'service', 'weekly_availability')
    raw_id_fields = ('chat_session',)
    readonly_fields = ('created_time', 'updated_time')
