# Generated by Django 3.2.20 on 2023-11-01 15:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('errata', '0004_alter_scanningsession_options'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ScanningSession',
        ),
    ]
