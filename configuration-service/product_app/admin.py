from django.contrib import admin
from django.contrib.admin.views.main import ChangeList

from .models import FAQ, Product


class ProductChangeList(ChangeList):
    """Loads the listed products' order quantities in one query, instead of one per row."""

    def get_results(self, request):
        super().get_results(request)
        self.result_list = Product.load_stock(self.result_list)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'business',
        'price',
        'total_quantity',
        'quantity_available',
        'quantity_on_hold',
        'quantity_sold',
        'is_active',
    )
    # Derived from the orders (checkout_app.stock); Product.clean() keeps total_quantity ≥ on hold + sold.
    readonly_fields = ('quantity_available', 'quantity_on_hold', 'quantity_sold')
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'description', 'information')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)

    def get_changelist(self, request, **kwargs):
        return ProductChangeList


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'business')
    list_filter = ('business',)
    search_fields = ('question', 'answer')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
