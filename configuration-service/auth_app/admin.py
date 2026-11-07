from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import BusinessUser


@admin.register(BusinessUser)
class BusinessUserAdmin(UserAdmin):
    # Reuse Django's user admin (password hashing, permissions UI) and add the business link and plan.
    fieldsets = (
        *UserAdmin.fieldsets,
        ('Business', {'fields': ('business', 'subscription_tier')}),
        ('Google / Facebook login', {'fields': ('firebase_uid',)}),
    )
    add_fieldsets = (*UserAdmin.add_fieldsets, ('Business', {'fields': ('business',)}))
    list_display = ('username', 'email', 'business', 'subscription_tier', 'is_staff', 'is_superuser', 'is_active')
    list_filter = (*UserAdmin.list_filter, 'business', 'subscription_tier')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    readonly_fields = ('firebase_uid',)
