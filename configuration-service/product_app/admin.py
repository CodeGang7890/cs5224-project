from django import forms
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList

from .models import BOOKED_LETTERS, FAQ, SLOT_AVAILABLE, Product, Service, ServiceProvider, WeeklyAvailability


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


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'description', 'is_active')
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'description')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)


@admin.register(WeeklyAvailability)
class WeeklyAvailabilityAdmin(admin.ModelAdmin):
    """Edits here aren't checked like the API (booked blocks stay H / X): prefer the Service tab."""

    list_display = ('service_provider', 'week', 'open_hours', 'booked_hours')
    list_filter = ('service_provider__business', 'service_provider')
    search_fields = ('service_provider__name',)
    list_select_related = ('service_provider',)
    autocomplete_fields = ('service_provider',)
    date_hierarchy = 'week'

    @admin.display(description='Open hours')
    def open_hours(self, obj) -> float:
        return obj.availability.count(SLOT_AVAILABLE) / 4

    @admin.display(description='Booked hours')
    def booked_hours(self, obj) -> float:
        return sum(obj.availability.count(letter) for letter in BOOKED_LETTERS) / 4


class ServiceAdminForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        business = cleaned.get('business')
        others = [p.name for p in cleaned.get('service_providers') or [] if business and p.business_id != business.pk]
        if others:
            self.add_error('service_providers', f"Not this business's service provider: {', '.join(others)}.")
        return cleaned


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    form = ServiceAdminForm
    list_display = ('name', 'business', 'price', 'duration_minutes', 'buffer_minutes', 'start_interval_minutes', 'is_active')
    list_filter = ('is_active', 'business')
    search_fields = ('name', 'description', 'information')
    list_select_related = ('business',)
    autocomplete_fields = ('business',)
    filter_horizontal = ('service_providers',)
