from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import BusinessUser


@admin.register(BusinessUser)
class BusinessUserAdmin(UserAdmin):
    # Reuse Django's user admin (password hashing, permissions UI) and add the business link.
    fieldsets = (*UserAdmin.fieldsets, ('Business', {'fields': ('business',)}))
    add_fieldsets = (*UserAdmin.add_fieldsets, ('Business', {'fields': ('business',)}))
    list_display = ('username', 'email', 'business', 'is_staff', 'is_superuser', 'is_active')
    list_filter = (*UserAdmin.list_filter, 'business')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
