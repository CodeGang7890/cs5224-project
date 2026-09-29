from django.contrib import admin

from .models import ChatConfiguration, ChatSession


@admin.register(ChatConfiguration)
class ChatConfigurationAdmin(admin.ModelAdmin):
    list_display = ('business', 'last_updated')
    list_filter = ('business',)
    search_fields = ('business__business_name',)
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    readonly_fields = ('last_updated',)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'display_name', 'business', 'chat_state_id', 'last_chat_time')
    list_filter = ('business',)
    search_fields = ('phone_number', 'display_name', 'business__business_name')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    readonly_fields = ('created_time',)
