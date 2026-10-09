# Service providers (a photographer, a teacher, a venue...), each with one WeeklyAvailability per
# week, instead of one recurring weekly template per calendar. Step 1 of 2 (with checkout_app 0003
# and product_app 0007): each old template becomes a service provider, linked to the same services,
# with its template as the current week and the next three (old X / H "not bookable" blocks become U).

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

WEEKS_FROM_TEMPLATE = 4


def current_monday():
    today = datetime.now(ZoneInfo(settings.SCHEDULE_TIME_ZONE)).date()
    return today - timedelta(days=today.weekday())


def to_providers(apps, schema_editor):
    WeeklyAvailability = apps.get_model('product_app', 'WeeklyAvailability')
    ServiceProvider = apps.get_model('product_app', 'ServiceProvider')
    monday = current_monday()
    for template in list(WeeklyAvailability.objects.all()):
        provider = ServiceProvider.objects.create(business_id=template.business_id, name=template.name)
        for service in template.services.all():
            service.service_providers.add(provider)
        week = ''.join('O' if letter == 'O' else 'U' for letter in template.availability)
        template.service_provider, template.week, template.availability = provider, monday, week
        template.save(update_fields=['service_provider', 'week', 'availability'])
        for offset in range(1, WEEKS_FROM_TEMPLATE):
            later = monday + timedelta(weeks=offset)
            WeeklyAvailability.objects.create(
                service_provider=provider, week=later, availability=week,
                business_id=template.business_id, name=f'{template.name} {later.isoformat()}',  # removed in 0007
            )


class Migration(migrations.Migration):

    dependencies = [
        ('configuration_app', '0001_initial'),
        ('product_app', '0005_weeklyavailability_service'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. "Mei Lin" or "Studio A" (not shown to customers).', max_length=150)),
                ('description', models.CharField(blank=True, help_text='Optional note for the business, e.g. "Lead photographer".', max_length=300)),
                ('is_active', models.BooleanField(default=True, help_text='Inactive providers take no new bookings.')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='service_providers', to='configuration_app.businessconfiguration')),
            ],
            options={
                'ordering': ['business', 'name'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('name', ''), _negated=True), name='service_provider_name_not_empty'),
                    models.UniqueConstraint(fields=('business', 'name'), name='service_provider_name_unique_per_business', violation_error_message='This business already has a service provider with this name.'),
                ],
            },
        ),
        migrations.AddField(
            model_name='service',
            name='service_providers',
            field=models.ManyToManyField(blank=True, help_text='The service providers (e.g. photographers) who can do this service.', related_name='services', to='product_app.serviceprovider'),
        ),
        migrations.RemoveConstraint(model_name='weeklyavailability', name='weekly_availability_valid'),
        migrations.RemoveConstraint(model_name='weeklyavailability', name='weekly_availability_name_unique_per_business'),
        migrations.AddField(
            model_name='weeklyavailability',
            name='service_provider',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='weekly_availabilities', to='product_app.serviceprovider'),
        ),
        migrations.AddField(
            model_name='weeklyavailability',
            name='week',
            field=models.DateField(null=True),
        ),
        migrations.RunPython(to_providers, migrations.RunPython.noop),  # backwards: the data stays as it is
    ]
