from django.contrib import admin

from .models import FAQ, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'business',
        'price',
        'quantity_available',
        'quantity_on_hold',
        'quantity_sold',
        'is_active',
    )
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'description', 'information')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'business')
    list_filter = ('business',)
    search_fields = ('question', 'answer')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
