"""Makes payment_reference required (0005 filled it in), with a new random one by default."""

from django.db import migrations, models

import checkout_app.models


def payment_reference_field():
    return models.CharField(
        db_index=True,
        default=checkout_app.models.new_payment_reference,
        editable=False,
        help_text='Random 128-bit reference (32 hex characters) the payment is made under.',
        max_length=32,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('checkout_app', '0005_payment_reference'),
    ]

    operations = [
        migrations.AlterField('orderitem', 'payment_reference', payment_reference_field()),
        migrations.AlterField('scheduleitem', 'payment_reference', payment_reference_field()),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(
                condition=models.Q(('payment_reference__regex', '^[0-9a-f]{32}$')),
                name='order_item_payment_reference_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='scheduleitem',
            constraint=models.CheckConstraint(
                condition=models.Q(('payment_reference__regex', '^[0-9a-f]{32}$')),
                name='schedule_item_payment_reference_valid',
            ),
        ),
    ]
