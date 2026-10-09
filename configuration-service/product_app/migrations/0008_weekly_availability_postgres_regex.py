# The letters constraint as days of blocks (`^([OUHX]{96}){7}$`): PostgreSQL rejects regex repeat
# counts over 255, so 0007's `^[OUHX]{672}$` failed on every insert there (SQLite allows it).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_app', '0007_weekly_availability_per_week'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='weeklyavailability',
            name='weekly_availability_letters_valid',
        ),
        migrations.AddConstraint(
            model_name='weeklyavailability',
            constraint=models.CheckConstraint(condition=models.Q(('availability__regex', '^([OUHX]{96}){7}$')), name='weekly_availability_letters_valid'),
        ),
    ]
