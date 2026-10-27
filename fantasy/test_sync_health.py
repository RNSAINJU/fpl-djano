from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from urllib.error import URLError

from .models import CaptainGameweekScore, LeagueEntry
from .management.commands.sync_fpl_data import Command as SyncCommand


class FplSyncHealthTests(TestCase):
    def setUp(self):
        LeagueEntry.objects.create(
            manager_name='Manager', team_name='Team', total_points=100,
            gameweek_points=50, rank=1,
        )

    def bootstrap(self, latest):
        return {'events': [
            {'id': latest, 'finished': True},
            {'id': latest + 1, 'finished': False},
        ]}

    @patch('fantasy.management.commands.check_fpl_sync_health._get_json')
    def test_healthy_latest_gameweek_passes(self, get_json):
        get_json.return_value = self.bootstrap(5)
        CaptainGameweekScore.objects.create(
            entry_id=10, manager_name='Manager', team_name='Team', gameweek=5,
            gameweek_points=50, captain_points=20,
        )
        output = StringIO()

        call_command('check_fpl_sync_health', stdout=output)

        self.assertIn('latest finished GW5', output.getvalue())

    @patch('fantasy.management.commands.check_fpl_sync_health._get_json')
    def test_stale_gameweek_fails(self, get_json):
        get_json.return_value = self.bootstrap(6)
        CaptainGameweekScore.objects.create(
            entry_id=10, manager_name='Manager', team_name='Team', gameweek=5,
        )

        with self.assertRaisesMessage(CommandError, 'GW6 has 0 stored manager rows'):
            call_command('check_fpl_sync_health')

    @patch('fantasy.management.commands.check_fpl_sync_health._get_json')
    def test_incomplete_gameweek_fails(self, get_json):
        get_json.return_value = self.bootstrap(5)
        LeagueEntry.objects.create(
            manager_name='Second', team_name='Second Team', total_points=90,
            gameweek_points=45, rank=2,
        )
        CaptainGameweekScore.objects.create(
            entry_id=10, manager_name='Manager', team_name='Team', gameweek=5,
        )

        with self.assertRaisesMessage(CommandError, 'has 1 stored manager rows; expected at least 2'):
            call_command('check_fpl_sync_health')


class FplSyncRetryTests(TestCase):
    def setUp(self):
        self.command = SyncCommand()
        self.bootstrap = {
            'events': [{'id': 5, 'finished': True}],
            'elements': [{'id': 100, 'web_name': 'Captain'}],
        }
        self.entry_rows = [{
            'entry': 10,
            'player_first_name': 'Test',
            'player_last_name': 'Manager',
            'entry_name': 'Test Team',
        }]

    @patch('fantasy.management.commands.sync_fpl_data._get_json')
    def test_live_points_failure_leaves_rows_retryable(self, get_json):
        get_json.side_effect = URLError('temporary outage')
        with patch.object(self.command, '_fetch_league_entry_rows', return_value=(self.entry_rows, True)):
            with self.assertRaisesMessage(CommandError, 'missing rows were left retryable'):
                self.command._sync_captain_scores(self.bootstrap, 6232)

        self.assertFalse(CaptainGameweekScore.objects.exists())

    @patch('fantasy.management.commands.sync_fpl_data._get_json')
    def test_picks_failure_leaves_rows_retryable(self, get_json):
        def response(url):
            if '/live/' in url:
                return {'elements': [{'id': 100, 'stats': {'total_points': 10}}]}
            raise URLError('temporary outage')

        get_json.side_effect = response
        with patch.object(self.command, '_fetch_league_entry_rows', return_value=(self.entry_rows, True)):
            with self.assertRaisesMessage(CommandError, 'missing rows were left retryable'):
                self.command._sync_captain_scores(self.bootstrap, 6232)

        self.assertFalse(CaptainGameweekScore.objects.exists())

    @patch('fantasy.management.commands.sync_fpl_data._get_json')
    def test_partial_league_pagination_does_not_replace_stored_standings(self, get_json):
        existing = LeagueEntry.objects.create(
            entry_id=99,
            manager_name='Existing',
            team_name='Existing Team',
            total_points=100,
            gameweek_points=50,
            rank=1,
        )
        get_json.side_effect = [
            {
                'standings': {
                    'results': [{'entry': 10, 'player_name': 'Partial', 'entry_name': 'Partial Team'}],
                    'has_next': True,
                },
            },
            URLError('page two unavailable'),
        ]

        with self.assertRaisesMessage(CommandError, 'Could not fetch complete standings data'):
            self.command._sync_league(6232)

        self.assertEqual(list(LeagueEntry.objects.values_list('pk', flat=True)), [existing.pk])
