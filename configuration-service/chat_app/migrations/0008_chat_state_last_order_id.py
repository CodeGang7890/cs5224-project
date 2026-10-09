# Once an order is placed, the chat now goes back to the start (so the customer can order again),
# keeping only `last_order_id`, instead of staying at Confirmation with `completed` / `order_id`.

from django.db import migrations


def to_last_order_id(apps, schema_editor):
    ChatSession = apps.get_model('chat_app', 'ChatSession')
    for session in ChatSession.objects.all():
        data = session.chat_state_data if isinstance(session.chat_state_data, dict) else {}
        if 'completed' not in data and 'order_id' not in data:
            continue
        order_id = data.get('order_id')
        if data.get('completed'):  # the order was placed: back to the start
            session.chat_state_id = 'start'
            session.chat_state_data = {'last_order_id': order_id} if order_id else {}
        else:
            session.chat_state_data = {k: v for k, v in data.items() if k not in ('completed', 'order_id')}
            if order_id:
                session.chat_state_data['last_order_id'] = order_id
        session.save(update_fields=['chat_state_id', 'chat_state_data'])


def to_completed(apps, schema_editor):
    ChatSession = apps.get_model('chat_app', 'ChatSession')
    for session in ChatSession.objects.all():
        data = session.chat_state_data if isinstance(session.chat_state_data, dict) else {}
        if 'last_order_id' not in data:
            continue
        rest = {k: v for k, v in data.items() if k != 'last_order_id'}
        if session.chat_state_id == 'start' and not rest:
            session.chat_state_id = 'confirmation'
            session.chat_state_data = {'completed': True, 'order_id': data['last_order_id']}
        else:
            session.chat_state_data = rest
        session.save(update_fields=['chat_state_id', 'chat_state_data'])


class Migration(migrations.Migration):

    dependencies = [
        ('chat_app', '0007_fixed_chat_flow'),
    ]

    operations = [
        migrations.RunPython(to_last_order_id, to_completed),
    ]
