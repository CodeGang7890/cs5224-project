from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('configuration_app', '0011_connection_method_default_labels')]

    operations = [
        migrations.AddField(
            model_name='businessconfiguration',
            name='payment_expiry_minutes',
            field=models.PositiveIntegerField(
                default=180,
                validators=[MinValueValidator(1)],
                help_text='Minutes after a new payment link is issued before it expires. Existing links are unchanged.',
            ),
        ),
        migrations.AddConstraint(
            model_name='businessconfiguration',
            constraint=models.CheckConstraint(
                condition=models.Q(payment_expiry_minutes__gte=1),
                name='business_payment_expiry_positive',
            ),
        ),
    ]
