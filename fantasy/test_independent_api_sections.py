from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class IndependentLeagueApiSectionTests(TestCase):
    @patch('fantasy.views._resolved_league_dataset')
    @patch('fantasy.views._fetch_manager_achievements')
    def test_achievements_does_not_resolve_league(self, fetch_achievements, resolve_league):
        fetch_achievements.return_value = {'awards': 3}

        response = self.client.get(
            reverse('fantasy:league_live_data'),
            {'section': 'achievements', 'entry_id': '123'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'achievements': {'awards': 3}})
        fetch_achievements.assert_called_once_with(123)
        resolve_league.assert_not_called()

    @patch('fantasy.views._resolved_league_dataset')
    @patch('fantasy.views._fetch_gameweek_fixtures_page')
    def test_live_fixtures_does_not_resolve_league(self, fetch_fixtures, resolve_league):
        fetch_fixtures.return_value = {'gameweek': 8, 'fixtures': []}

        response = self.client.get(
            reverse('fantasy:league_live_data'),
            {'section': 'live_fixtures', 'gameweek': '8'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'live_fixtures_page': {'gameweek': 8, 'fixtures': []},
        })
        fetch_fixtures.assert_called_once_with(8)
        resolve_league.assert_not_called()
