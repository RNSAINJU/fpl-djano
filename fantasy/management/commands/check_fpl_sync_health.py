import json
from urllib import error, request

from django.core.management.base import BaseCommand, CommandError

from fantasy.models import CaptainGameweekScore, LeagueEntry


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


class Command(BaseCommand):
    help = 'Fail if data for the latest finished FPL gameweek is missing or incomplete.'

    def handle(self, *args, **options):
        try:
            bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            raise CommandError(f'Could not reach the FPL API for the health check: {exc}') from exc

        finished = [event.get('id') for event in bootstrap.get('events', []) if event.get('finished')]
        finished = [gameweek for gameweek in finished if isinstance(gameweek, int)]
        if not finished:
            self.stdout.write(self.style.SUCCESS('FPL sync healthy: no finished gameweeks yet.'))
            return

        latest_finished = max(finished)
        expected_managers = LeagueEntry.objects.count()
        if expected_managers == 0:
            raise CommandError('FPL sync unhealthy: league standings contain no managers.')

        stored_rows = CaptainGameweekScore.objects.filter(gameweek=latest_finished).count()
        if stored_rows < expected_managers:
            raise CommandError(
                f'FPL sync unhealthy: GW{latest_finished} has {stored_rows} stored manager rows; '
                f'expected at least {expected_managers} from the current league standings.'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'FPL sync healthy: latest finished GW{latest_finished} has '
                f'{stored_rows}/{expected_managers} manager rows.'
            )
        )
