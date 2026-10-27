import bleach
from django.db import migrations, models


ALLOWED_TAGS = {'p', 'br', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'a'}
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}


def sanitize_site_html(apps, schema_editor):
    SiteSettings = apps.get_model('fantasy', 'SiteSettings')
    for settings in SiteSettings.objects.all():
        changed = []
        for field_name in (
            'captain_leaderboard_note',
            'captain_recommendation_note',
            'monthly_winner_note',
        ):
            original = getattr(settings, field_name) or ''
            cleaned = bleach.clean(
                original,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                protocols={'http', 'https', 'mailto'},
                strip=True,
            )
            if cleaned != original:
                setattr(settings, field_name, cleaned)
                changed.append(field_name)
        if changed:
            settings.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ('fantasy', '0015_sitesettings_about_description_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='leagueentry',
            name='entry_id',
            field=models.PositiveIntegerField(blank=True, null=True, unique=True),
        ),
        migrations.RunPython(sanitize_site_html, migrations.RunPython.noop),
    ]
