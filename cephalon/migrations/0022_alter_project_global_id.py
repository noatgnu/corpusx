# Generated by Django 5.0 on 2023-12-16 18:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cephalon', '0021_rename_websocketinterchange_pyre_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='global_id',
            field=models.TextField(blank=True, null=True),
        ),
    ]
