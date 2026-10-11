# The detail fields split in two (the user asked): product orders (Details collection) and
# service bookings (Booking details) ask for their own details. Both start as the old list, without
# phone fields: customers chat on WhatsApp, so the chat already has their number (and the phone
# type is gone).

import chat_app.validators
from django.db import migrations, models

DEFAULT_DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': 'text', 'max_length': 150},
    {'key': 'email', 'label': 'Email', 'type': 'email'},
]


def without_phone(fields) -> list[dict]:
    """The fields minus any phone field; the defaults if no required field is left."""
    kept = [field for field in fields or [] if isinstance(field, dict) and field.get('type') != 'phone']
    if not any(field.get('required', True) is not False for field in kept):
        return [dict(field) for field in DEFAULT_DETAIL_FIELDS]
    return kept


def split_detail_fields(apps, schema_editor):
    ChatConfiguration = apps.get_model('chat_app', 'ChatConfiguration')
    for config in ChatConfiguration.objects.all():
        fields = without_phone(config.product_detail_fields)
        config.product_detail_fields = fields
        config.schedule_detail_fields = [dict(field) for field in fields]
        config.save(update_fields=['product_detail_fields', 'schedule_detail_fields'])


def merge_detail_fields(apps, schema_editor):
    """Backwards: the old single list is the product one (the schedule one is dropped)."""


class Migration(migrations.Migration):

    dependencies = [
        ('chat_app', '0010_chat_configuration_welcome_and_style'),
    ]

    operations = [
        migrations.RenameField(model_name='chatconfiguration', old_name='detail_fields', new_name='product_detail_fields'),
        migrations.AlterField(
            model_name='chatconfiguration',
            name='product_detail_fields',
            field=models.JSONField(
                default=chat_app.validators.default_detail_fields,
                help_text='The customer details the Details collection step asks for, for product orders (see validators.detail_field_errors).',
                validators=[chat_app.validators.validate_detail_fields],
            ),
        ),
        migrations.AddField(
            model_name='chatconfiguration',
            name='schedule_detail_fields',
            field=models.JSONField(
                default=chat_app.validators.default_detail_fields,
                help_text='The customer details the Booking details step asks for, for service bookings (see validators.detail_field_errors).',
                validators=[chat_app.validators.validate_detail_fields],
            ),
        ),
        migrations.RunPython(split_detail_fields, merge_detail_fields),
    ]
