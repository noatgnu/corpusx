# Generated by Django 5.0 on 2023-12-11 12:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cephalon', '0008_alter_chunkedupload_chunk_size_projectfilecontent'),
    ]

    operations = [
        migrations.CreateModel(
            name='APIKeyRemote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.TextField(blank=True, null=True)),
                ('key', models.TextField(unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('hostname', models.TextField(blank=True, null=True)),
                ('protocol', models.TextField(blank=True, null=True)),
                ('port', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='Topic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.TextField(blank=True, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddField(
            model_name='apikey',
            name='access_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='apikey',
            name='public_key',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='access_topics',
            field=models.ManyToManyField(blank=True, to='cephalon.topic'),
        ),
    ]
