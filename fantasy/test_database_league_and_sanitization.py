from unittest.mock import patch

from django.test import TestCase

from .models import CaptainGameweekScore, LeagueEntry, SiteSettings
from .views import _fetch_league_roster, _resolved_league_dataset


class DatabaseLeagueDatasetTests(TestCase):
    @patch('fantasy.views._fetch_fpl_league_entries')
    def test_synced_database_is_preferred_over_live_api(self, fetch_live):
        LeagueEntry.objects.create(
            entry_id=123,
            manager_name='Manager',
            team_name='Team',
            total_points=400,
            gameweek_points=60,
            rank=1,
        )
        CaptainGameweekScore.objects.create(
            entry_id=123,
            manager_name='Manager',
            team_name='Team',
            gameweek=5,
            event_transfers_cost=4,
        )

        rows, league_name, error, source = _resolved_league_dataset()

        self.assertEqual(rows[0]['total_points'], 400)
        self.assertEqual(rows[0]['hits'], 4)
        self.assertEqual(league_name, 'FPL Bhaktapur S8')
        self.assertIsNone(error)
        self.assertEqual(source, 'synced')
        fetch_live.assert_not_called()

    @patch('fantasy.views._fetch_league_roster_live')
    def test_synced_roster_is_reused_by_other_league_pages(self, fetch_live_roster):
        LeagueEntry.objects.create(
            entry_id=123,
            manager_name='Manager',
            team_name='Team',
            total_points=400,
            gameweek_points=60,
            rank=1,
        )

        rows, using_new_entries, league_name = _fetch_league_roster(6232)

        self.assertEqual(rows[0]['entry'], 123)
        self.assertEqual(rows[0]['player_name'], 'Manager')
        self.assertFalse(using_new_entries)
        self.assertEqual(league_name, 'FPL Bhaktapur S8')
        fetch_live_roster.assert_not_called()


class SiteSettingsSanitizationTests(TestCase):
    def test_notes_keep_basic_formatting_and_remove_unsafe_html(self):
        settings = SiteSettings.load()
        settings.captain_leaderboard_note = (
            '<strong>Safe</strong><script>alert(1)</script>'
            '<a href="javascript:alert(2)" onclick="alert(3)">link</a>'
            '<img src=x onerror=alert(4)>'
        )
        settings.save()
        settings.refresh_from_db()

        self.assertIn('<strong>Safe</strong>', settings.captain_leaderboard_note)
        self.assertNotIn('<script', settings.captain_leaderboard_note)
        self.assertNotIn('javascript:', settings.captain_leaderboard_note)
        self.assertNotIn('onclick', settings.captain_leaderboard_note)
        self.assertNotIn('<img', settings.captain_leaderboard_note)
