"""Adds payment_reference to orders and bookings.

AddField with a callable default would give every existing row the same value (Django evaluates it
once), so: add the column nullable and give each existing row its own reference here; 0006 makes it
required. Two migrations (two transactions) because PostgreSQL refuses to ALTER a table with pending
deferred foreign-key trigger events, which updating the rows leaves behind.
"""

from django.db import migrations, models

import checkout_app.models


def fill_payment_references(apps, schema_editor):
    for model_name in ('OrderItem', 'ScheduleItem'):
        model = apps.get_model('checkout_app', model_name)
        rows = list(model.objects.filter(payment_reference__isnull=True).only('pk'))
        for row in rows:
            row.payment_reference = checkout_app.models.new_payment_reference()
        model.objects.bulk_update(rows, ['payment_reference'], batch_size=500)


def payment_reference_field(**kwargs):
    return models.CharField(
        db_index=True,
        editable=False,
        help_text='Random 128-bit reference (32 hex characters) the payment is made under.',
        max_length=32,
        **kwargs,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('checkout_app', '0004_payment_failed_status'),
    ]

    operations = [
        migrations.AddField('orderitem', 'payment_reference', payment_reference_field(null=True)),
        migrations.AddField('scheduleitem', 'payment_reference', payment_reference_field(null=True)),
        migrations.RunPython(fill_payment_references, migrations.RunPython.noop),
    ]
