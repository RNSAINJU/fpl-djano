import os
import runpy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import CaptainGameweekScore, Season
from .views import SeasonArchiveError, _archive_current_season


class SeasonArchiveTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Test season')
        CaptainGameweekScore.objects.create(
            entry_id=10, gameweek=1, manager_name='Manager', team_name='Team',
            gameweek_points=50, captain_points=20,
        )
        self.row = dict(rank=1, entry_id=10, manager_name='Manager', team_name='Team',
                        total_points=50, gameweek_points=50, monthly_points=50, captain_points=20)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        defaults = {
            '_fetch_fpl_league_entries_live': ([self.row], 'Test league', None),
            '_get_json': {'events': [{'id': 1, 'finished': True, 'deadline_time': '2026-08-15T12:00:00Z'}]},
            '_fetch_gameweek_leaderboard_live': {'winner': self.row, 'gameweek_error': None},
            '_fetch_monthly_leaderboard_live': {'monthly_winner': self.row, 'monthly_error': None},
            '_fetch_captain_leaderboard_live': ([self.row], 'Final', None),
        }
        for name, value in defaults.items():
            self.mocks[name] = self.stack.enter_context(patch(f'fantasy.views.{name}', return_value=value))

    def assert_empty_archive(self):
        self.season.refresh_from_db()
        self.assertEqual(self.season.league_name, '')
        for relation in ('standings', 'gameweek_winners', 'monthly_winners', 'captain_standings'):
            self.assertFalse(getattr(self.season, relation).exists())

    def test_complete_archive(self):
        self.assertEqual(_archive_current_season(self.season, league_id=42), {
            'standings': 1, 'gameweek_winners': 1, 'monthly_winners': 1, 'captain_standings': 1,
        })
        self.mocks['_fetch_fpl_league_entries_live'].assert_called_once_with(42)
        self.assertEqual(self.season.monthly_winners.get().month_label, 'August 2026')
        self.assertEqual(self.season.captain_standings.get().captain_points, 20)

    def test_upstream_failures_roll_back_every_section(self):
        failures = {
            '_fetch_fpl_league_entries_live': ([self.row], 'Test league', 'API unavailable'),
            '_fetch_gameweek_leaderboard_live': {'winner': self.row, 'gameweek_error': 'API unavailable'},
            '_fetch_monthly_leaderboard_live': {'monthly_winner': self.row, 'monthly_error': 'API unavailable'},
            '_fetch_captain_leaderboard_live': ([self.row], 'Final', 'API unavailable'),
        }
        for name, result in failures.items():
            with self.subTest(name=name):
                original = self.mocks[name].return_value
                self.mocks[name].return_value = result
                with self.assertRaises(SeasonArchiveError):
                    _archive_current_season(self.season)
                self.assert_empty_archive()
                self.mocks[name].return_value = original

    def test_metadata_outage_leaves_no_archive_rows(self):
        self.mocks['_get_json'].side_effect = URLError('offline')
        with self.assertRaises(SeasonArchiveError):
            _archive_current_season(self.season)
        self.assert_empty_archive()

    def test_empty_results_are_rejected(self):
        for name, result in (
            ('_fetch_fpl_league_entries_live', ([], 'League', None)),
            ('_fetch_gameweek_leaderboard_live', {'winner': None}),
            ('_fetch_monthly_leaderboard_live', {'monthly_winner': None}),
            ('_fetch_captain_leaderboard_live', ([], 'Final', None)),
        ):
            with self.subTest(name=name):
                original = self.mocks[name].return_value
                self.mocks[name].return_value = result
                with self.assertRaises(SeasonArchiveError):
                    _archive_current_season(self.season)
                self.assert_empty_archive()
                self.mocks[name].return_value = original

    def test_unfinished_season_is_rejected(self):
        self.mocks['_get_json'].return_value['events'][0]['finished'] = False
        with self.assertRaises(SeasonArchiveError):
            _archive_current_season(self.season)
        self.assert_empty_archive()

    def test_missing_synced_gameweeks_are_rejected(self):
        CaptainGameweekScore.objects.all().delete()
        with self.assertRaises(SeasonArchiveError):
            _archive_current_season(self.season)
        self.assert_empty_archive()

    def test_admin_failure_rolls_back_new_season_and_reports_error(self):
        self.client.force_login(get_user_model().objects.create_superuser('admin', password='test-password'))
        self.mocks['_fetch_captain_leaderboard_live'].return_value = ([], 'Final', 'offline')
        response = self.client.post(reverse('fantasy_admin:fantasy_season_add'), {'name': 'Failed season', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Season.objects.filter(name='Failed season').exists())
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Archive not created' in str(message) for message in messages))
        self.assertFalse(any(message.level == 25 for message in messages))


class SettingsEnvironmentTests(SimpleTestCase):
    def load_settings(self, env):
        with patch.dict(os.environ, env, clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parent.parent / 'fplsite' / 'settings.py'))

    def test_missing_blank_and_old_development_secrets_are_rejected(self):
        for secret in ('', '   ', 'django-insecure-old-key'):
            with self.subTest(secret=secret), self.assertRaises(ImproperlyConfigured):
                self.load_settings({'DJANGO_SECRET_KEY': secret})
        with self.assertRaises(ImproperlyConfigured):
            self.load_settings({})

    def test_debug_defaults_off(self):
        settings = self.load_settings({'DJANGO_SECRET_KEY': 'test-only-private-key'})
        self.assertFalse(settings['DEBUG'])
        self.assertEqual(settings['SECRET_KEY'], 'test-only-private-key')

    def test_development_debug_is_explicit(self):
        settings = self.load_settings({'DJANGO_SECRET_KEY': 'test-only-private-key', 'DJANGO_DEBUG': 'true'})
        self.assertTrue(settings['DEBUG'])


class GameweekTransferHitTests(TestCase):
    def setUp(self):
        self.roster = [
            {'entry': 1, 'player_name': 'Manager A', 'entry_name': 'Team A'},
            {'entry': 2, 'player_name': 'Manager B', 'entry_name': 'Team B'},
        ]
        for entry, gw, points, hits in [(1, 1, 100, 8), (1, 2, 70, 4), (2, 2, 69, 0), (1, 3, 90, 4)]:
            CaptainGameweekScore.objects.create(entry_id=entry, gameweek=gw,
                gameweek_points=points, event_transfers_cost=hits)

    def leaderboard(self, selected, live=False):
        from .views import _fetch_gameweek_leaderboard_live
        events = [{'id': gw, 'finished': not (live and gw == 2), 'is_current': gw == 2}
                  for gw in (1, 2)]
        def api(url):
            if 'bootstrap-static' in url:
                return {'events': events}
            return {'picks': [{'element': 10, 'multiplier': 1}],
                    'entry_history': {'event_transfers_cost': 4}}
        with patch('fantasy.views._get_json', side_effect=api), \
             patch('fantasy.views._fetch_league_entry_rows', return_value=(self.roster, False)), \
             patch('fantasy.views._fetch_live_element_points', return_value={10: 70}):
            return _fetch_gameweek_leaderboard_live(selected_gameweek=selected)

    def test_finished_scores_and_ranking_deduct_hits(self):
        data = self.leaderboard(2)
        rows = {row['entry_id']: row for row in data['entries']}
        self.assertIsNone(data['gameweek_error'])
        self.assertEqual(rows[1]['gameweek_points'], 66)
        self.assertEqual(rows[1]['total_points'], 158)
        self.assertEqual(rows[1]['hits'], 4)
        self.assertEqual(rows[2]['gameweek_points'], 69)
        self.assertEqual(data['winner']['entry_id'], 2)

    def test_historical_total_excludes_future_weeks(self):
        data = self.leaderboard(1)
        row = next(row for row in data['entries'] if row['entry_id'] == 1)
        self.assertEqual(row['gameweek_points'], 92)
        self.assertEqual(row['total_points'], 92)

    def test_live_hits_are_deducted_once_and_stored_live_row_is_excluded(self):
        data = self.leaderboard(2, live=True)
        row = next(row for row in data['entries'] if row['entry_id'] == 1)
        self.assertEqual(row['gameweek_points'], 66)
        self.assertEqual(row['total_points'], 158)
        self.assertEqual(row['hits'], 4)


class AboutUsPageTests(TestCase):
    def test_page_displays_admin_content_as_text(self):
        from .models import SiteSettings
        settings = SiteSettings.load()
        settings.about_description = '<script>alert(1)</script> Community description'
        settings.about_history = 'Our first season was memorable.'
        settings.contact_email = 'organizer@example.com'
        settings.save()
        response = self.client.get(reverse('fantasy:about_us'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Our first season was memorable.')
        self.assertContains(response, 'mailto:organizer@example.com')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'class="active" href="/about-us/"')

    def test_blank_contact_details_have_no_empty_links(self):
        from .models import SiteSettings
        settings = SiteSettings.load()
        settings.contact_email = settings.contact_phone = settings.contact_address = ''
        settings.save()
        response = self.client.get(reverse('fantasy:about_us'))
        self.assertContains(response, 'Contact details will be shared here soon.')
        self.assertNotContains(response, 'mailto:')


class GameweekHistoryTests(TestCase):
    def setUp(self):
        self.roster = [
            {'entry': 1, 'player_name': 'Manager A', 'entry_name': 'Team A'},
            {'entry': 2, 'player_name': 'Manager B', 'entry_name': 'Team B'},
        ]
        scores = [
            (1, 1, 100, 8, 'Captain A', 20),
            (1, 2, 70, 4, 'Captain B', 12),
            (2, 1, 95, 0, 'Captain C', 18),
            (2, 2, 69, 0, 'Captain D', 14),
        ]
        for entry, gameweek, points, hits, captain, captain_points in scores:
            CaptainGameweekScore.objects.create(
                entry_id=entry,
                gameweek=gameweek,
                gameweek_points=points,
                event_transfers_cost=hits,
                captain_name=captain,
                captain_points=captain_points,
            )

    def test_selected_gameweek_shows_net_scores_and_cumulative_total(self):
        from .views import _fetch_gameweek_history
        with patch('fantasy.views._fetch_league_roster', return_value=(self.roster, False, 'League')):
            data = _fetch_gameweek_history(selected_gameweek='2')

        self.assertEqual(data['gameweek_history_ids'], [1, 2])
        self.assertEqual(data['selected_gameweek'], 2)
        self.assertEqual(data['league_name'], 'League')
        rows = {row['entry_id']: row for row in data['gameweek_history_rows']}
        self.assertEqual(rows[1]['gameweek_points'], 66)
        self.assertEqual(rows[1]['total_points'], 158)
        self.assertEqual(rows[1]['hits'], 4)
        self.assertEqual(rows[1]['captain_name'], 'Captain B')
        self.assertEqual(rows[2]['rank'], 1)
        self.assertEqual(rows[1]['rank'], 2)

    def test_invalid_gameweek_defaults_to_latest_finished_week(self):
        from .views import _fetch_gameweek_history
        with patch('fantasy.views._fetch_league_roster', return_value=(self.roster, False, 'League')):
            data = _fetch_gameweek_history(selected_gameweek='99')
        self.assertEqual(data['selected_gameweek'], 2)

    def test_page_passes_selected_gameweek_and_renders_picker(self):
        history = {
            'gameweek_history_ids': [1, 2],
            'selected_gameweek': 1,
            'gameweek_history_rows': [],
        }
        with patch('fantasy.views._base_page_context', return_value={'active_page': 'gameweekhistory'}), \
             patch('fantasy.views._is_season_finished', return_value=False), \
             patch('fantasy.views._fetch_gameweek_history', return_value=history) as fetch_history:
            response = self.client.get(reverse('fantasy:gameweekhistory'), {'gameweek': '1'})
        self.assertEqual(response.status_code, 200)
        fetch_history.assert_called_once_with(selected_gameweek='1')
        self.assertContains(response, '<option value="1" selected>Gameweek 1</option>', html=True)
        self.assertNotContains(response, '<th>GW2</th>')


class PrizePageTests(TestCase):
    def test_each_competition_displays_its_cash_prize(self):
        from .models import PageAdvertisement
        expected = {
            PageAdvertisement.Page.CAPTAIN_MODE: 'Winner — Rs. 5,000',
            PageAdvertisement.Page.CLASSIC_LEAGUE: '1st place — Rs. 15,000',
            PageAdvertisement.Page.GAMEWEEK_WINNERS: 'Every gameweek winner — Rs. 500',
            PageAdvertisement.Page.MANAGER_OF_THE_MONTH: 'Every Manager of the Month — Rs. 1,000',
        }
        for page, prize in expected.items():
            PageAdvertisement.objects.update_or_create(
                page=page,
                defaults={'image': f'advertisements/{page}.png'},
            )

        with patch('fantasy.views._base_page_context', return_value={'active_page': 'prizes'}):
            response = self.client.get(reverse('fantasy:prizes'))

        self.assertEqual(response.status_code, 200)
        for prize in expected.values():
            self.assertContains(response, prize)
        self.assertContains(response, '2nd place — Rs. 10,000')
        self.assertContains(response, '3rd place — Rs. 8,000')
