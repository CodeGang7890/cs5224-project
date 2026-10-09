# Step 3 of 3 (see 0006): a WeeklyAvailability is one service provider's one week.

import django.db.models.deletion
from django.db import migrations, models

import product_app.models


class Migration(migrations.Migration):

    dependencies = [
        ('product_app', '0006_service_providers'),
        ('checkout_app', '0003_scheduleitem_service_provider'),
    ]

    operations = [
        migrations.RemoveField(model_name='service', name='weekly_availability'),
        migrations.RemoveConstraint(model_name='weeklyavailability', name='weekly_availability_name_not_empty'),
        migrations.RemoveField(model_name='weeklyavailability', name='name'),
        migrations.RemoveField(model_name='weeklyavailability', name='business'),
        migrations.AlterField(
            model_name='weeklyavailability',
            name='service_provider',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='weekly_availabilities', to='product_app.serviceprovider'),
        ),
        migrations.AlterField(
            model_name='weeklyavailability',
            name='week',
            field=models.DateField(help_text='The Monday of the week.', validators=[product_app.models.validate_monday]),
        ),
        migrations.AlterField(
            model_name='weeklyavailability',
            name='availability',
            field=models.CharField(default=product_app.models.default_availability, help_text='672 letters, one per 15-minute block from Monday 00:00 (local time): O = available, U = unavailable, H = on hold (booked, payment pending), X = booked. Bookings set H and X.', max_length=672, validators=[product_app.models.validate_availability]),
        ),
        migrations.AlterModelOptions(
            name='weeklyavailability',
            options={'ordering': ['service_provider', 'week'], 'verbose_name_plural': 'weekly availabilities'},
        ),
        migrations.AddConstraint(
            model_name='weeklyavailability',
            constraint=models.UniqueConstraint(fields=('service_provider', 'week'), name='weekly_availability_unique_week', violation_error_message='This service provider already has an availability for this week.'),
        ),
        migrations.AddConstraint(
            model_name='weeklyavailability',
            constraint=models.CheckConstraint(condition=models.Q(('availability__regex', '^[OUHX]{672}$')), name='weekly_availability_letters_valid'),
        ),
    ]
