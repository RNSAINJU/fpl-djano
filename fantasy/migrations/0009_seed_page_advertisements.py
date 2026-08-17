from django.db import migrations


def seed_page_advertisements(apps, schema_editor):
    PageAdvertisement = apps.get_model('fantasy', 'PageAdvertisement')
    pages = ['captain_mode', 'classic_league', 'gameweek_winners', 'manager_of_the_month']
    for page in pages:
        PageAdvertisement.objects.get_or_create(page=page)


def remove_page_advertisements(apps, schema_editor):
    PageAdvertisement = apps.get_model('fantasy', 'PageAdvertisement')
    PageAdvertisement.objects.filter(
        page__in=['captain_mode', 'classic_league', 'gameweek_winners', 'manager_of_the_month']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fantasy', '0008_pageadvertisement'),
    ]

    operations = [
        migrations.RunPython(seed_page_advertisements, remove_page_advertisements),
    ]
