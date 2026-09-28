from django.contrib import admin

from .models import BusinessConfiguration


@admin.register(BusinessConfiguration)
class BusinessConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'business_name', 'location')
    search_fields = ('business_name', 'location')  # also enables autocomplete from other admins
