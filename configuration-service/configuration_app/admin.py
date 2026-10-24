from django.contrib import admin

from .models import BusinessConfiguration, WhatsAppConfiguration


@admin.register(BusinessConfiguration)
class BusinessConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'business_name', 'location')
    search_fields = ('business_name', 'location')  # also enables autocomplete from other admins


@admin.register(WhatsAppConfiguration)
class WhatsAppConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        'business',
        'phone_number_id',
        'display_phone_number',
        'verified_name',
        'connection_method',
        'status',
        'last_updated',
    )
    search_fields = ('business__business_name', 'phone_number_id', 'display_phone_number', 'verified_name')
    list_select_related = ('business',)
    list_filter = ('connection_method', 'status', 'last_updated')
    autocomplete_fields = ('business',)
    # The secrets are never shown here; businesses connect with Facebook (Embedded Signup) in the frontend.
    exclude = ('access_token', 'app_secret')
    readonly_fields = (
        'display_phone_number',
        'verified_name',
        'verify_token',
        'connection_method',
        'waba_id',
        'status',
        'status_event',
        'status_updated_time',
        'created_time',
        'last_updated',
    )

    def has_add_permission(self, request) -> bool:
        return False  # adding needs the secrets, which this form doesn't show
