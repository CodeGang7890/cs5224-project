from django.contrib import admin

from .models import ChatConfiguration


@admin.register(ChatConfiguration)
class ChatConfigurationAdmin(admin.ModelAdmin):
    list_display = ('business', 'last_updated')
    list_filter = ('business',)
    search_fields = ('business__business_name',)
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    readonly_fields = ('last_updated',)
