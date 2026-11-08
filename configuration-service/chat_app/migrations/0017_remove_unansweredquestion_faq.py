# Separate from 0016: PostgreSQL refuses ALTER TABLE after 0016's row updates in the same
# transaction ("pending trigger events").

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chat_app', '0016_unanswered_question_answer'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='unansweredquestion',
            name='faq',
        ),
    ]
