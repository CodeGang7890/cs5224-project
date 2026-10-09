# Step 2 of 3 (see product_app 0006): bookings are made with a service provider, and are written
# into the provider's weeks (H while pending payment, X once paid or completed).

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

SLOT = timedelta(minutes=15)


def to_providers(apps, schema_editor):
    ScheduleItem = apps.get_model('checkout_app', 'ScheduleItem')
    WeeklyAvailability = apps.get_model('product_app', 'WeeklyAvailability')
    tz = ZoneInfo(settings.SCHEDULE_TIME_ZONE)
    rows = {}

    def row(provider, monday):
        key = (provider.pk, monday)
        if key not in rows:
            found = WeeklyAvailability.objects.filter(service_provider=provider, week=monday).first()
            if found is None:  # a week the old template didn't cover: start from it (the provider's first week)
                template = WeeklyAvailability.objects.filter(service_provider=provider).order_by('week').first()
                found = WeeklyAvailability.objects.create(
                    service_provider=provider, week=monday,
                    availability=template.availability if template else 'U' * 672,
                    business_id=provider.business_id, name=f'{provider.name} {monday.isoformat()}',
                )
            rows[key] = [found, list(found.availability)]
        return rows[key][1]

    for item in ScheduleItem.objects.exclude(weekly_availability=None).select_related('weekly_availability'):
        provider = item.weekly_availability.service_provider
        item.service_provider = provider
        item.save(update_fields=['service_provider'])
        letter = 'H' if item.order_status == 'pending_payment' else 'X'
        moment = item.start_time
        while moment < item.blocked_until:
            local = moment.astimezone(tz)
            letters = row(provider, local.date() - timedelta(days=local.weekday()))
            index = local.weekday() * 96 + (local.hour * 60 + local.minute) // 15
            if moment < item.end_time or letters[index] != 'U':  # the buffer only where it was open
                if letters[index] != 'X':
                    letters[index] = letter
            moment += SLOT
    for found, letters in rows.values():
        found.availability = ''.join(letters)
        found.save(update_fields=['availability'])
    if schema_editor.connection.vendor == 'postgresql':
        # Run the deferred foreign key checks of the rows written above now: PostgreSQL refuses to
        # ALTER a table (or CREATE INDEX, which Django leaves to the end of the migration) with
        # pending trigger events, and the next operations alter scheduleitem.
        schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')


class Migration(migrations.Migration):

    dependencies = [
        ('checkout_app', '0002_scheduleitem'),
        ('product_app', '0006_service_providers'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleitem',
            name='service_provider',
            field=models.ForeignKey(blank=True, help_text='Who it is booked with (e.g. which photographer).', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_items', to='product_app.serviceprovider'),
        ),
        migrations.RunPython(to_providers, migrations.RunPython.noop),  # backwards: the data stays as it is
        migrations.RemoveIndex(model_name='scheduleitem', name='schedule_item_calendar'),
        migrations.RemoveField(model_name='scheduleitem', name='weekly_availability'),
        migrations.AddIndex(
            model_name='scheduleitem',
            index=models.Index(fields=['service_provider', 'start_time'], name='schedule_item_provider_time'),
        ),
    ]
