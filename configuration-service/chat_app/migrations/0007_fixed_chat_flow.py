# The chat flow is fixed now (router + order steps), instead of a graph of blocks built by each
# business: ChatConfiguration.config_json becomes detail_fields (the Details collection step's
# settings), and ChatSession.chat_state_id becomes a step key instead of a block id.

import copy

import chat_app.validators
from django.db import migrations, models

DEFAULT_DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': 'text', 'max_length': 150},
    {'key': 'email', 'label': 'Email', 'type': 'email'},
]
STEP_BY_BLOCK_TYPE = {
    'PRODUCT_SELECTION_BLOCK': 'product_selection',
    'DETAILS_COLLECTION_BLOCK': 'details_collection',
    'CONFIRMATION_BLOCK': 'confirmation',
}
CHAT_STEPS = ['start', 'product_selection', 'details_collection', 'confirmation']


def _find_block(config_json, block_id):
    # Block ids are compared type-strictly, as the old flow did ("1" is not block 1).
    for block in config_json if isinstance(config_json, list) else []:
        if isinstance(block, dict) and type(block.get('id')) is type(block_id) and block.get('id') == block_id:
            return block
    return None


def to_fixed_flow(apps, schema_editor):
    ChatConfiguration = apps.get_model('chat_app', 'ChatConfiguration')
    ChatSession = apps.get_model('chat_app', 'ChatSession')
    configs = {}
    for config in ChatConfiguration.objects.all():
        configs[config.business_id] = config
        # The first Details collection block's fields (none, or no fields: the defaults).
        blocks = [b for b in config.config_json or [] if isinstance(b, dict)]
        details = next((b for b in blocks if b.get('block_type') == 'DETAILS_COLLECTION_BLOCK'), None)
        config.detail_fields = (details or {}).get('fields') or copy.deepcopy(DEFAULT_DETAIL_FIELDS)
        config.save(update_fields=['detail_fields'])
    for session in ChatSession.objects.all():
        config = configs.get(session.business_id)
        block = _find_block(config.config_json, session.old_chat_state_id) if config else None
        # Start, Send message, or a block that no longer exists: start (no order in progress).
        session.chat_step = STEP_BY_BLOCK_TYPE.get((block or {}).get('block_type'), 'start')
        session.save(update_fields=['chat_step'])


def to_block_graph(apps, schema_editor):
    """Backwards: every configuration becomes Start → Product selection → Details collection →
    Confirmation (block ids 1–4), with the detail fields on its Details collection block."""
    ChatConfiguration = apps.get_model('chat_app', 'ChatConfiguration')
    ChatSession = apps.get_model('chat_app', 'ChatSession')
    block_types = ['START_BLOCK', 'PRODUCT_SELECTION_BLOCK', 'DETAILS_COLLECTION_BLOCK', 'CONFIRMATION_BLOCK']
    with_config = set()
    for config in ChatConfiguration.objects.all():
        with_config.add(config.business_id)
        config_json = [
            {
                'id': index + 1,
                'next_block_id': index + 2 if index < 3 else None,
                'block_type': block_type,
                'position_x': 100 + 300 * index,
                'position_y': 100,
            }
            for index, block_type in enumerate(block_types)
        ]
        config_json[2]['fields'] = config.detail_fields
        config.config_json = config_json
        config.save(update_fields=['config_json'])
    for session in ChatSession.objects.all():
        has_config = session.business_id in with_config
        session.old_chat_state_id = CHAT_STEPS.index(session.chat_step) + 1 if has_config else None
        session.save(update_fields=['old_chat_state_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('chat_app', '0006_unansweredquestion'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatconfiguration',
            name='detail_fields',
            field=models.JSONField(
                default=chat_app.validators.default_detail_fields,
                help_text='The customer details the Details collection step asks for (see validators.detail_field_errors).',
                validators=[chat_app.validators.validate_detail_fields],
            ),
        ),
        migrations.AlterField(
            model_name='chatconfiguration',
            name='config_json',
            field=models.JSONField(default=list, validators=[chat_app.validators.validate_chat_config]),
        ),
        migrations.RenameField(model_name='chatsession', old_name='chat_state_id', new_name='old_chat_state_id'),
        migrations.AddField(
            model_name='chatsession',
            name='chat_step',
            field=models.CharField(
                choices=[
                    ('start', 'Start'),
                    ('product_selection', 'Product selection'),
                    ('details_collection', 'Details collection'),
                    ('confirmation', 'Confirmation'),
                ],
                default='start',
                help_text='The chat flow step the customer is at: start (no order in progress) or an order step.',
                max_length=32,
            ),
        ),
        migrations.RunPython(to_fixed_flow, to_block_graph),
        migrations.RemoveField(model_name='chatconfiguration', name='config_json'),
        migrations.RemoveField(model_name='chatsession', name='old_chat_state_id'),
        migrations.RenameField(model_name='chatsession', old_name='chat_step', new_name='chat_state_id'),
        migrations.AddConstraint(
            model_name='chatsession',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('chat_state_id__in', ['start', 'product_selection', 'details_collection', 'confirmation'])
                ),
                name='chat_session_step_valid',
            ),
        ),
    ]
