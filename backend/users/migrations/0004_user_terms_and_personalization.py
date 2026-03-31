from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_prompthistory_music_picker_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='personalization_opt_in',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='terms_accepted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
