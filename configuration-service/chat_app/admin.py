from django.contrib import admin

from .models import ChatConfiguration, ChatSession, InboundMessage, OutboundMessage, UnansweredQuestion


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
    list_filter = ('business', 'chat_state_id', 'is_sandbox')
    search_fields = ('phone_number', 'display_name', 'business__business_name')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    readonly_fields = ('created_time',)


@admin.register(UnansweredQuestion)
class UnansweredQuestionAdmin(admin.ModelAdmin):
    list_display = ('question', 'business', 'chat_session', 'status', 'created_time', 'answered_time')
    list_filter = ('status', 'business')
    search_fields = ('question', 'business__business_name', 'chat_session__display_name', 'chat_session__phone_number')
    list_select_related = ('business', 'chat_session')
    autocomplete_fields = ('business', 'chat_session')
    readonly_fields = ('created_time',)



@admin.register(InboundMessage)
class InboundMessageAdmin(admin.ModelAdmin):
    """WhatsApp messages messaging-service took from Pub/Sub (read only: it writes them)."""

    list_display = ('message_id', 'business', 'chat_session', 'status', 'received_time', 'replied_time')
    list_filter = ('status', 'business')
    search_fields = ('message_id', 'chat_session__phone_number', 'business__business_name')
    list_select_related = ('business', 'chat_session')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OutboundMessage)
class OutboundMessageAdmin(admin.ModelAdmin):
    """WhatsApp replies messaging-service saved to send (its outbox; read only: it writes them)."""

    list_display = ('id', 'business', 'chat_session', 'status', 'attempts', 'created_time', 'sent_time')
    list_filter = ('status', 'business')
    search_fields = ('text', 'meta_message_id', 'chat_session__phone_number', 'business__business_name')
    list_select_related = ('business', 'chat_session')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
