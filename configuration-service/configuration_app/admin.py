from django.contrib import admin

from .models import BusinessConfiguration, WhatsAppConfiguration


@admin.register(BusinessConfiguration)
class BusinessConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'business_name', 'location')
    search_fields = ('business_name', 'location')  # also enables autocomplete from other admins


@admin.register(WhatsAppConfiguration)
class WhatsAppConfigurationAdmin(admin.ModelAdmin):
    list_display = ('business', 'phone_number_id', 'display_phone_number', 'verified_name', 'last_updated')
    search_fields = ('business__business_name', 'phone_number_id', 'display_phone_number', 'verified_name')
    list_select_related = ('business',)
    list_filter = ('last_updated',)
    autocomplete_fields = ('business',)
    # The secrets are never shown here; owners enter them from the frontend (Home → WhatsApp).
    exclude = ('access_token', 'app_secret')
    readonly_fields = ('display_phone_number', 'verified_name', 'verify_token', 'created_time', 'last_updated')

    def has_add_permission(self, request) -> bool:
        return False  # adding needs the secrets, which this form doesn't show
