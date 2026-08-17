import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib import error, request

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fantasy.models import CaptainGameweekScore, Fixture, LeagueEntry, Player, Team

FPL_CLASSIC_LEAGUE_ID = 6232

POSITION_MAP = {
    1: Player.Position.GOALKEEPER,
    2: Player.Position.DEFENDER,
    3: Player.Position.MIDFIELDER,
    4: Player.Position.FORWARD,
}


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def _photo_url_from_code(code) -> str:
    if not code:
        return ''
    return f'https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png'


class Command(BaseCommand):
    help = (
        'Sync Team, Player, Fixture, league standings and captain gameweek '
        'scores from the live FPL API, so the admin panel and public site '
        'reflect real, current data instead of placeholder rows.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=int,
            default=FPL_CLASSIC_LEAGUE_ID,
            help='Classic league ID to sync standings from (default: the site-wide league).',
        )
        parser.add_argument(
            '--skip-league',
            action='store_true',
            help='Skip syncing mini-league standings.',
        )
        parser.add_argument(
            '--skip-captain-scores',
            action='store_true',
            help='Skip syncing per-gameweek captain scores.',
        )

    def handle(self, *args, **options):
        try:
            bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            raise CommandError(f'Could not reach the FPL API: {exc}') from exc

        team_map = self._sync_teams(bootstrap.get('teams', []))
        self._sync_players(bootstrap.get('elements', []), team_map)
        self._sync_fixtures(team_map)

        if not options['skip_league']:
            self._sync_league(options['league_id'])

        if not options['skip_captain_scores']:
            self._sync_captain_scores(bootstrap, options['league_id'])

        self.stdout.write(self.style.SUCCESS('FPL data sync complete.'))

    def _sync_teams(self, teams_payload):
        team_map = {}
        seen_ids = []
        for row in teams_payload:
            team, _created = Team.objects.update_or_create(
                fpl_id=row['id'],
                defaults={
                    'name': row.get('name', ''),
                    'short_name': row.get('short_name', ''),
                    'strength': row.get('strength') or 3,
                },
            )
            team_map[row['id']] = team
            seen_ids.append(row['id'])

        removed, _ = Team.objects.exclude(fpl_id__in=seen_ids).exclude(fpl_id__isnull=True).delete()
        self.stdout.write(f'Teams synced: {len(seen_ids)} (removed {removed} stale)')
        return team_map

    def _sync_players(self, elements_payload, team_map):
        seen_ids = []
        for row in elements_payload:
            team = team_map.get(row.get('team'))
            if not team:
                continue
            name = row.get('web_name') or f"{row.get('first_name', '')} {row.get('second_name', '')}".strip()
            Player.objects.update_or_create(
                fpl_id=row['id'],
                defaults={
                    'name': name or 'Unknown',
                    'team': team,
                    'position': POSITION_MAP.get(row.get('element_type'), Player.Position.MIDFIELDER),
                    'price': (row.get('now_cost') or 0) / 10,
                    'total_points': row.get('total_points') or 0,
                    'selected_by_percent': row.get('selected_by_percent') or 0,
                    'goals': row.get('goals_scored') or 0,
                    'assists': row.get('assists') or 0,
                    'clean_sheets': row.get('clean_sheets') or 0,
                    'photo_url': _photo_url_from_code(row.get('code')),
                },
            )
            seen_ids.append(row['id'])

        removed, _ = Player.objects.exclude(fpl_id__in=seen_ids).exclude(fpl_id__isnull=True).delete()
        self.stdout.write(f'Players synced: {len(seen_ids)} (removed {removed} stale)')

    def _sync_fixtures(self, team_map):
        try:
            fixtures_payload = _get_json('https://fantasy.premierleague.com/api/fixtures/?future=1')
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            self.stdout.write(self.style.WARNING(f'Skipped fixtures: {exc}'))
            return

        seen_ids = []
        for row in fixtures_payload:
            kickoff_iso = row.get('kickoff_time')
            if not kickoff_iso:
                continue
            home_team = team_map.get(row.get('team_h'))
            away_team = team_map.get(row.get('team_a'))
            if not home_team or not away_team:
                continue
            kickoff_dt = datetime.fromisoformat(kickoff_iso.replace('Z', '+00:00'))
            difficulty = max(
                row.get('team_h_difficulty') or 3,
                row.get('team_a_difficulty') or 3,
            )
            Fixture.objects.update_or_create(
                fpl_id=row['id'],
                defaults={
                    'home_team': home_team,
                    'away_team': away_team,
                    'kickoff': timezone.make_aware(kickoff_dt.replace(tzinfo=None)) if timezone.is_naive(kickoff_dt) else kickoff_dt,
                    'gameweek': row.get('event') or 1,
                    'difficulty': difficulty,
                },
            )
            seen_ids.append(row['id'])

        removed, _ = Fixture.objects.exclude(fpl_id__in=seen_ids).exclude(fpl_id__isnull=True).delete()
        self.stdout.write(f'Fixtures synced: {len(seen_ids)} (removed {removed} stale)')

    def _fetch_league_pages(self, league_id, page_param, result_key, max_pages=200):
        base_url = f'https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/'
        page = 1
        rows = []
        while page <= max_pages:
            params = {'page_standings': 1, 'page_new_entries': 1, page_param: page}
            url = f'{base_url}?' + '&'.join(f'{k}={v}' for k, v in params.items())
            try:
                payload = _get_json(url)
            except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
                self.stdout.write(self.style.WARNING(f'Stopped paginating {result_key} at page {page}: {exc}'))
                break
            section = payload.get(result_key, {})
            rows.extend(section.get('results', []))
            if not section.get('has_next'):
                break
            page += 1
        return rows

    def _fetch_league_entry_rows(self, league_id):
        """Returns (rows, using_new_entries). Falls back to newly-joined
        entries when the league hasn't produced scored standings yet (e.g.
        pre-season) - same fallback the public site uses."""
        standings = self._fetch_league_pages(league_id, 'page_standings', 'standings')
        if standings:
            return standings, False
        new_entries = self._fetch_league_pages(league_id, 'page_new_entries', 'new_entries')
        return new_entries, True

    def _sync_league(self, league_id):
        standings, using_new_entries = self._fetch_league_entry_rows(league_id)
        if not using_new_entries:
            entries = [
                LeagueEntry(
                    manager_name=(item.get('player_name', '').strip() or 'Unknown Manager'),
                    team_name=item.get('entry_name', 'Unknown Team'),
                    total_points=item.get('total', 0),
                    gameweek_points=item.get('event_total', 0),
                    rank=item.get('rank') or index,
                )
                for index, item in enumerate(standings, start=1)
            ]
        else:
            entries = [
                LeagueEntry(
                    manager_name=(
                        f"{item.get('player_first_name', '')} {item.get('player_last_name', '')}".strip()
                        or 'New Manager'
                    ),
                    team_name=item.get('entry_name', 'Unknown Team'),
                    total_points=0,
                    gameweek_points=0,
                    rank=index,
                )
                for index, item in enumerate(standings, start=1)
            ]

        if not entries:
            self.stdout.write(self.style.WARNING('League fetched, but no members were returned yet.'))
            return

        LeagueEntry.objects.all().delete()
        LeagueEntry.objects.bulk_create(entries)
        self.stdout.write(f'League standings synced: {len(entries)} entries')

    def _sync_captain_scores(self, bootstrap, league_id):
        """Backfills CaptainGameweekScore for every FINISHED gameweek that
        isn't already stored. Finished gameweeks' points never change again,
        so once a (manager, gameweek) row is saved it's never re-fetched -
        this is what keeps the season-total leaderboard fast as the season
        goes on, instead of re-fetching every manager's picks for every past
        gameweek on every sync."""
        events = bootstrap.get('events', [])
        finished_gameweeks = sorted(event['id'] for event in events if event.get('finished'))
        if not finished_gameweeks:
            self.stdout.write('No finished gameweeks yet - nothing to backfill for captain scores.')
            return

        player_name_lookup = {el['id']: el.get('web_name', 'Unknown') for el in bootstrap.get('elements', [])}

        entry_rows, using_new_entries = self._fetch_league_entry_rows(league_id)
        if not entry_rows:
            self.stdout.write(self.style.WARNING('No league entries found - skipping captain score sync.'))
            return

        already_synced = set(
            CaptainGameweekScore.objects.filter(gameweek__in=finished_gameweeks).values_list('entry_id', 'gameweek')
        )

        to_fetch = []
        for row in entry_rows:
            entry_id = row.get('entry')
            if not entry_id:
                continue
            if using_new_entries:
                manager_name = (
                    f"{row.get('player_first_name', '')} {row.get('player_last_name', '')}".strip() or 'New Manager'
                )
            else:
                manager_name = row.get('player_name', '').strip() or 'Unknown Manager'
            team_name = row.get('entry_name', 'Unknown Team')
            for gameweek in finished_gameweeks:
                if (entry_id, gameweek) not in already_synced:
                    to_fetch.append((entry_id, manager_name, team_name, gameweek))

        if not to_fetch:
            self.stdout.write('Captain scores already up to date for all finished gameweeks.')
            return

        # Fetch each needed gameweek's live points once and share it across
        # every manager, rather than re-fetching per manager.
        live_points_by_gw = {}
        for gameweek in sorted({item[3] for item in to_fetch}):
            try:
                payload = _get_json(f'https://fantasy.premierleague.com/api/event/{gameweek}/live/')
                live_points_by_gw[gameweek] = {
                    el['id']: el.get('stats', {}).get('total_points', 0) for el in payload.get('elements', [])
                }
            except (error.HTTPError, error.URLError, ValueError, TimeoutError) as exc:
                self.stdout.write(self.style.WARNING(f'Could not fetch live points for GW{gameweek}: {exc}'))
                live_points_by_gw[gameweek] = {}

        def fetch_one(item):
            entry_id, manager_name, team_name, gameweek = item
            captain_name = '-'
            captain_points = 0
            gameweek_points = 0
            event_transfers_cost = 0
            try:
                picks_payload = _get_json(
                    f'https://fantasy.premierleague.com/api/entry/{entry_id}/event/{gameweek}/picks/'
                )
                entry_history = picks_payload.get('entry_history', {})
                gameweek_points = entry_history.get('points', 0)
                event_transfers_cost = entry_history.get('event_transfers_cost', 0)
                captain_pick = next((p for p in picks_payload.get('picks', []) if p.get('is_captain')), None)
                if captain_pick:
                    element_id = captain_pick.get('element')
                    multiplier = captain_pick.get('multiplier') or 2
                    captain_points = live_points_by_gw.get(gameweek, {}).get(element_id, 0) * multiplier
                    captain_name = player_name_lookup.get(element_id, 'Unknown')
            except (error.HTTPError, error.URLError, ValueError, TimeoutError):
                pass
            return entry_id, manager_name, team_name, gameweek, captain_name, captain_points, gameweek_points, event_transfers_cost

        saved = 0
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(fetch_one, item) for item in to_fetch]
            for future in as_completed(futures):
                entry_id, manager_name, team_name, gameweek, captain_name, captain_points, gameweek_points, event_transfers_cost = future.result()
                CaptainGameweekScore.objects.update_or_create(
                    entry_id=entry_id,
                    gameweek=gameweek,
                    defaults={
                        'manager_name': manager_name,
                        'team_name': team_name,
                        'captain_name': captain_name,
                        'captain_points': captain_points,
                        'gameweek_points': gameweek_points,
                        'event_transfers_cost': event_transfers_cost,
                    },
                )
                saved += 1

        self.stdout.write(f'Captain scores backfilled: {saved} manager x gameweek rows across GW{finished_gameweeks}')
