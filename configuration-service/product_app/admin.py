from django import forms
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList

from .models import FAQ, SLOT_AVAILABLE, Product, Service, WeeklyAvailability


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


@admin.register(WeeklyAvailability)
class WeeklyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'open_hours')
    list_filter = ('business',)
    search_fields = ('name',)
    list_select_related = ('business',)
    autocomplete_fields = ('business',)

    @admin.display(description='Open hours / week')
    def open_hours(self, obj) -> float:
        return obj.availability.count(SLOT_AVAILABLE) / 4


class ServiceAdminForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        business = cleaned.get('business')
        others = [a.name for a in cleaned.get('weekly_availability') or [] if business and a.business_id != business.pk]
        if others:
            self.add_error('weekly_availability', f"Not this business's weekly availability: {', '.join(others)}.")
        return cleaned


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    form = ServiceAdminForm
    list_display = ('name', 'business', 'price', 'duration_minutes', 'buffer_minutes', 'is_active')
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'description', 'information')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    filter_horizontal = ('weekly_availability',)
