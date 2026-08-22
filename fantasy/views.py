import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib import error, request
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db.models import F, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import (
	CaptainGameweekScore,
	PageAdvertisement,
	Season,
	SeasonCaptainStanding,
	SeasonGameweekWinner,
	SeasonMonthlyWinner,
	SeasonStanding,
)

FPL_CLASSIC_LEAGUE_ID = 6232

# Fixture kickoff times come from the FPL API in UTC. The dashboard displays
# them in Nepal time (Kathmandu, UTC+5:45) rather than the site's UTC clock.
NEPAL_TZ = ZoneInfo('Asia/Kathmandu')

# How long live FPL data (league standings, captain/monthly leaderboards,
# dashboard) is cached before the next request re-fetches it live. A cache
# miss on these means fanning out to dozens of live FPL API calls, which
# can take several seconds - 15 minutes trades a bit of freshness for far
# fewer visitors ever hitting that cold path, without the data feeling
# stale for a casual league.
FPL_CACHE_TIMEOUT = 900


def _get_json(url: str) -> dict:
	with request.urlopen(url, timeout=8) as response:
		return json.loads(response.read().decode('utf-8'))


def _photo_url_from_code(code: int | str | None) -> str:
	if not code:
		return ''
	return f'https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png'


def _shirt_url_from_code(code: int | str | None) -> str:
	"""The FPL app's own 3D-rendered team jersey icon, keyed by each team's
	`code` field from bootstrap-static (not its `id`)."""
	if not code:
		return ''
	return f'https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_{code}-66.png'


def _fetch_fpl_live_data(entry_id: int) -> tuple[dict | None, str | None]:
	base_url = 'https://fantasy.premierleague.com/api'
	try:
		entry = _get_json(f'{base_url}/entry/{entry_id}/')
		bootstrap = _get_json(f'{base_url}/bootstrap-static/')
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		target_event = current_event or next_event
		if not target_event:
			return None, 'Could not determine gameweek from FPL API.'

		current_gameweek = target_event.get('id')
		picks = {'picks': []}
		try:
			picks = _get_json(f'{base_url}/entry/{entry_id}/event/{current_gameweek}/picks/')
		except error.HTTPError:
			# Some entries have no published picks for upcoming gameweek yet.
			picks = {'picks': []}
		except (error.URLError, TimeoutError, ValueError, KeyError, TypeError):
			picks = {'picks': []}
		element_lookup = {element['id']: element for element in bootstrap.get('elements', [])}
		position_lookup = {
			1: 'GK',
			2: 'DEF',
			3: 'MID',
			4: 'FWD',
		}

		team_picks = []
		for pick in picks.get('picks', []):
			element = element_lookup.get(pick.get('element'))
			if not element:
				continue
			captain_tag = 'C' if pick.get('is_captain') else 'VC' if pick.get('is_vice_captain') else ''
			team_picks.append(
				{
					'name': element.get('web_name', 'Unknown'),
					'player_id': element.get('id'),
					'position': position_lookup.get(element.get('element_type'), '-'),
					'multiplier': pick.get('multiplier', 1),
					'captain_tag': captain_tag,
				}
			)

		data = {
			'entry_id': entry_id,
			'manager_name': f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip() or 'FPL Manager',
			'team_name': entry.get('name', 'Unknown Team'),
			'overall_points': entry.get('summary_overall_points', 0),
			'overall_rank': entry.get('summary_overall_rank', 0),
			'event_points': entry.get('summary_event_points', 0),
			'current_gameweek': current_gameweek,
			'picks': team_picks,
		}
		return data, None
	except error.HTTPError as exc:
		if exc.code == 404:
			return None, 'No FPL account found for this ID. Please check and try again.'
		return None, f'FPL API returned an error ({exc.code}). Please try again shortly.'
	except (error.URLError, TimeoutError):
		return None, 'Could not reach FPL API right now. Please try again in a moment.'
	except (ValueError, KeyError, TypeError):
		return None, 'Unexpected API response received. Please try again.'


def _fetch_player_history(player_id: int) -> tuple[dict | None, str | None]:
	base_url = 'https://fantasy.premierleague.com/api'
	try:
		bootstrap = _get_json(f'{base_url}/bootstrap-static/')
		element_lookup = {element['id']: element for element in bootstrap.get('elements', [])}
		team_lookup = {team['id']: team for team in bootstrap.get('teams', [])}
		element = element_lookup.get(player_id)
		if not element:
			return None, 'Player ID not found in FPL data.'

		summary = _get_json(f'{base_url}/element-summary/{player_id}/')
		team_name = team_lookup.get(element.get('team'), {}).get('name', 'Unknown Team')
		position_lookup = {
			1: 'Goalkeeper',
			2: 'Defender',
			3: 'Midfielder',
			4: 'Forward',
		}

		history_rows = []
		for row in summary.get('history', [])[-12:]:
			history_rows.append(
				{
					'gameweek': row.get('round'),
					'opponent_team': row.get('opponent_team'),
					'minutes': row.get('minutes', 0),
					'goals_scored': row.get('goals_scored', 0),
					'assists': row.get('assists', 0),
					'clean_sheets': row.get('clean_sheets', 0),
					'total_points': row.get('total_points', 0),
				}
			)

		past_seasons = []
		for season in summary.get('history_past', []):
			past_seasons.append(
				{
					'season_name': season.get('season_name', '-'),
					'total_points': season.get('total_points', 0),
					'goals_scored': season.get('goals_scored', 0),
					'assists': season.get('assists', 0),
				}
			)

		upcoming_fixtures = []
		for fixture in summary.get('fixtures', [])[:5]:
			is_home = fixture.get('is_home')
			opponent_id = fixture.get('team_a') if is_home else fixture.get('team_h')
			opponent_name = team_lookup.get(opponent_id, {}).get('short_name', 'TBD')
			upcoming_fixtures.append(
				{
					'gameweek': fixture.get('event'),
					'opponent': opponent_name,
					'is_home': is_home,
					'difficulty': fixture.get('difficulty'),
				}
			)

		payload = {
			'player_id': player_id,
			'player_name': element.get('web_name', 'Unknown Player'),
			'full_name': f"{element.get('first_name', '')} {element.get('second_name', '')}".strip(),
			'team_name': team_name,
			'position': position_lookup.get(element.get('element_type'), '-'),
			'current_price': (element.get('now_cost', 0) / 10),
			'selected_by': element.get('selected_by_percent', '0'),
			'history_rows': history_rows,
			'past_seasons': past_seasons,
			'upcoming_fixtures': upcoming_fixtures,
		}
		return payload, None
	except error.HTTPError as exc:
		if exc.code == 404:
			return None, 'No history found for this player ID.'
		return None, f'FPL API error while fetching player history ({exc.code}).'
	except (error.URLError, TimeoutError):
		return None, 'Could not reach FPL API for player history right now.'
	except (ValueError, KeyError, TypeError):
		return None, 'Unexpected data format received for player history.'


def _fetch_entry_history(entry_id: int) -> tuple[dict | None, str | None]:
	base_url = 'https://fantasy.premierleague.com/api'
	try:
		payload = _get_json(f'{base_url}/entry/{entry_id}/history/')
		current_rows = []
		for row in payload.get('current', [])[-12:]:
			current_rows.append(
				{
					'event': row.get('event'),
					'points': row.get('points', 0),
					'total_points': row.get('total_points', 0),
					'overall_rank': row.get('overall_rank', 0),
					'rank': row.get('rank', 0),
					'event_transfers': row.get('event_transfers', 0),
					'event_transfers_cost': row.get('event_transfers_cost', 0),
				}
			)

		past_rows = []
		for row in payload.get('past', []):
			past_rows.append(
				{
					'season_name': row.get('season_name', '-'),
					'total_points': row.get('total_points', 0),
					'rank': row.get('rank', 0),
				}
			)

		chips = []
		for row in payload.get('chips', []):
			chips.append(
				{
					'name': row.get('name', '-'),
					'event': row.get('event', 0),
				}
			)

		return {
			'current_rows': current_rows,
			'past_rows': past_rows,
			'chips': chips,
		}, None
	except error.HTTPError as exc:
		if exc.code == 404:
			return None, 'No history found for this FPL ID.'
		return None, f'FPL API error while fetching FPL ID history ({exc.code}).'
	except (error.URLError, TimeoutError):
		return None, 'Could not reach FPL API for FPL ID history right now.'
	except (ValueError, KeyError, TypeError):
		return None, 'Unexpected data format received for FPL ID history.'


def _to_float(value, default: float = 0.0) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _to_int(value, default: int = 0) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _build_captain_recommendations(entry_id: int) -> tuple[dict | None, str | None]:
	live_data, live_error = _fetch_fpl_live_data(entry_id)
	if live_error or not live_data:
		return None, live_error or 'Could not load team data for captain mode.'

	picks = live_data.get('picks', [])
	if not picks:
		return None, 'No squad picks available yet for this gameweek.'

	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return None, 'Could not load FPL stats required for captain recommendations.'

	element_lookup = {element['id']: element for element in bootstrap.get('elements', [])}

	scored_rows = []
	for pick in picks:
		element = element_lookup.get(pick.get('player_id'))
		if not element:
			continue

		form = _to_float(element.get('form'))
		points_per_game = _to_float(element.get('points_per_game'))
		ict_index = _to_float(element.get('ict_index'))
		selected_by = _to_float(element.get('selected_by_percent'))
		goals = _to_int(element.get('goals_scored'))
		assists = _to_int(element.get('assists'))
		clean_sheets = _to_int(element.get('clean_sheets'))
		minutes = _to_int(element.get('minutes'))
		availability = element.get('chance_of_playing_next_round')
		availability_score = 1.0 if availability is None else max(0.0, min(1.0, _to_float(availability) / 100.0))

		position = pick.get('position', '-')
		position_bonus_map = {
			'FWD': 1.4,
			'MID': 1.1,
			'DEF': 0.55,
			'GK': 0.35,
		}
		position_bonus = position_bonus_map.get(position, 0.2)
		minutes_score = min(1.0, minutes / 900.0) * 2.2

		captain_score = (
			(form * 4.1)
			+ (points_per_game * 2.9)
			+ (ict_index * 0.19)
			+ (goals * 0.26)
			+ (assists * 0.2)
			+ (clean_sheets * (0.12 if position in {'DEF', 'GK'} else 0.03))
			+ (selected_by * 0.05)
			+ minutes_score
			+ position_bonus
		)
		captain_score *= availability_score

		reason_bits = [
			f'Form {form:.1f}',
			f'PPG {points_per_game:.1f}',
			f'ICT {ict_index:.1f}',
		]
		if goals:
			reason_bits.append(f'Goals {goals}')
		if assists:
			reason_bits.append(f'Assists {assists}')
		if availability is not None and _to_int(availability) < 100:
			reason_bits.append(f'Availability {availability}%')

		scored_rows.append(
			{
				'name': pick.get('name', 'Unknown'),
				'player_id': pick.get('player_id'),
				'position': position,
				'captain_tag': pick.get('captain_tag') or '-',
				'form': round(form, 2),
				'points_per_game': round(points_per_game, 2),
				'ict_index': round(ict_index, 2),
				'selected_by': round(selected_by, 2),
				'availability': availability if availability is not None else 100,
				'captain_score': round(captain_score, 2),
				'reason': ' | '.join(reason_bits),
			}
		)

	if not scored_rows:
		return None, 'No valid players were found to score for captain mode.'

	scored_rows.sort(key=lambda row: row['captain_score'], reverse=True)
	captain_pick = scored_rows[0]
	vice_pick = scored_rows[1] if len(scored_rows) > 1 else None

	return {
		'live_data': live_data,
		'captain_pick': captain_pick,
		'vice_pick': vice_pick,
		'top_rows': scored_rows[:8],
	}, None


def _fetch_dashboard_data() -> dict:
	return cache.get_or_set('fpl:dashboard_data', _fetch_dashboard_data_live, timeout=FPL_CACHE_TIMEOUT)


def _fetch_dashboard_data_live() -> dict:
	position_lookup = {
		1: 'Goalkeeper',
		2: 'Defender',
		3: 'Midfielder',
		4: 'Forward',
	}
	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		fixture_rows = _get_json('https://fantasy.premierleague.com/api/fixtures/?future=1')
		elements = bootstrap.get('elements', [])
		teams = bootstrap.get('teams', [])
		team_lookup = {team['id']: team for team in teams}

		sorted_by_selected = sorted(
			elements,
			key=lambda row: (_to_float(row.get('selected_by_percent')), _to_int(row.get('total_points'))),
			reverse=True,
		)
		top_players = []
		for element in sorted_by_selected[:5]:
			team = team_lookup.get(element.get('team'), {})
			top_players.append(
				{
					'name': element.get('web_name', 'Unknown'),
					'team_short_name': team.get('short_name', '-'),
					'position_label': position_lookup.get(element.get('element_type'), '-'),
					'price': _to_int(element.get('now_cost')) / 10,
					'total_points': _to_int(element.get('total_points')),
					'selected_by_percent': element.get('selected_by_percent', '0'),
				}
			)

		def stat_leader(sort_key: str, position_types: set[int] | None = None) -> dict | None:
			eligible = elements
			if position_types is not None:
				eligible = [element for element in elements if element.get('element_type') in position_types]
			if not eligible:
				return None
			leader = max(eligible, key=lambda row: (_to_int(row.get(sort_key)), _to_int(row.get('total_points'))))
			return {
				'name': leader.get('web_name', 'Unknown'),
				'goals': _to_int(leader.get('goals_scored')),
				'assists': _to_int(leader.get('assists')),
				'clean_sheets': _to_int(leader.get('clean_sheets')),
				'photo_url': _photo_url_from_code(leader.get('code')),
			}

		top_scorer = stat_leader('goals_scored')
		top_assister = stat_leader('assists')
		top_clean_sheet = stat_leader('clean_sheets', {1, 2})

		upcoming_fixtures = []
		for fixture in sorted(
			[row for row in fixture_rows if row.get('kickoff_time') and not row.get('finished')],
			key=lambda row: row.get('kickoff_time'),
		)[:10]:
			home_team = team_lookup.get(fixture.get('team_h'), {})
			away_team = team_lookup.get(fixture.get('team_a'), {})
			kickoff_iso = fixture.get('kickoff_time')
			kickoff_display = '-'
			if kickoff_iso:
				kickoff_dt = datetime.fromisoformat(kickoff_iso.replace('Z', '+00:00'))
				kickoff_display = kickoff_dt.astimezone(NEPAL_TZ).strftime('%d %b, %H:%M') + ' NPT'
			upcoming_fixtures.append(
				{
					'home_team': {
						'short_name': home_team.get('short_name', '-'),
						'badge': home_team.get('short_name', 'H')[:1],
						'shirt_url': _shirt_url_from_code(home_team.get('code')),
					},
					'away_team': {
						'short_name': away_team.get('short_name', '-'),
						'badge': away_team.get('short_name', 'A')[:1],
						'shirt_url': _shirt_url_from_code(away_team.get('code')),
					},
					'kickoff_display': kickoff_display,
					'gameweek': fixture.get('event') or '-',
					'difficulty': max(_to_int(fixture.get('team_h_difficulty'), 3), _to_int(fixture.get('team_a_difficulty'), 3)),
				}
			)

		# Live Fixtures board: only the current (or next, pre-season)
		# gameweek's own matches, with their real live/finished status -
		# not just "the next 10 chronological fixtures", which spills into
		# the following gameweek once the current one is mostly played out.
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		target_event = current_event or next_event
		target_gameweek = target_event.get('id') if target_event else None

		live_fixtures = []
		if target_gameweek:
			try:
				gw_fixture_rows = _get_json(
					f'https://fantasy.premierleague.com/api/fixtures/?event={target_gameweek}'
				)
			except (error.HTTPError, error.URLError, ValueError, TimeoutError):
				gw_fixture_rows = []
			for fixture in sorted(gw_fixture_rows, key=lambda row: row.get('kickoff_time') or ''):
				home_team = team_lookup.get(fixture.get('team_h'), {})
				away_team = team_lookup.get(fixture.get('team_a'), {})
				kickoff_iso = fixture.get('kickoff_time')
				kickoff_display = '-'
				if kickoff_iso:
					kickoff_dt = datetime.fromisoformat(kickoff_iso.replace('Z', '+00:00'))
					kickoff_display = timezone.localtime(kickoff_dt).strftime('%d %b, %H:%M')

				if fixture.get('finished'):
					status = 'FT'
				elif fixture.get('started'):
					status = 'LIVE'
				else:
					status = 'Upcoming'

				live_fixtures.append(
					{
						'home_team': {
							'short_name': home_team.get('short_name', '-'),
							'badge': home_team.get('short_name', 'H')[:1],
						},
						'away_team': {
							'short_name': away_team.get('short_name', '-'),
							'badge': away_team.get('short_name', 'A')[:1],
						},
						'kickoff_display': kickoff_display,
						'status': status,
						'home_score': fixture.get('team_h_score'),
						'away_score': fixture.get('team_a_score'),
					}
				)

		return {
			'top_players': top_players,
			'top_scorer': top_scorer,
			'top_assister': top_assister,
			'top_clean_sheet': top_clean_sheet,
			'fixtures': upcoming_fixtures[:4],
			'live_fixtures': live_fixtures,
			'live_fixtures_label': f"GW {target_gameweek}" if target_gameweek else 'Upcoming',
			'teams_count': len(teams),
			'players_count': len(elements),
		}
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return {
			'top_players': [],
			'top_scorer': None,
			'top_assister': None,
			'top_clean_sheet': None,
			'fixtures': [],
			'live_fixtures': [],
			'live_fixtures_label': 'Upcoming',
			'teams_count': 0,
			'players_count': 0,
		}


def _get_countdown_context() -> dict:
	fallback_deadline = timezone.now() + timezone.timedelta(days=19, hours=11, minutes=34, seconds=52)
	context = {
		'gameweek_name': 'Gameweek 1',
		'deadline_iso': fallback_deadline.isoformat(),
		'deadline_display': fallback_deadline.strftime('%d/%m/%Y, %H:%M:%S'),
		'season_message': "The season hasn't kicked off yet",
	}

	base_url = 'https://fantasy.premierleague.com/api'
	try:
		bootstrap = _get_json(f'{base_url}/bootstrap-static/')
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		target_event = current_event or next_event or (events[0] if events else None)

		if target_event:
			context['gameweek_name'] = f"Gameweek {target_event.get('id', 1)}"
			deadline_time = target_event.get('deadline_time')
			if deadline_time:
				parsed_deadline = datetime.fromisoformat(deadline_time.replace('Z', '+00:00'))
				local_deadline = timezone.localtime(parsed_deadline)
				context['deadline_iso'] = local_deadline.isoformat()
				context['deadline_display'] = local_deadline.strftime('%d/%m/%Y, %H:%M:%S')

		if current_event:
			context['season_message'] = 'Live gameweek is active right now'
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		pass

	return context


def _base_page_context(active_page: str) -> dict:
	countdown = _get_countdown_context()
	return {
		'active_page': active_page,
		'gameweek_name': countdown['gameweek_name'],
		'deadline_iso': countdown['deadline_iso'],
		'deadline_display': countdown['deadline_display'],
		'season_message': countdown['season_message'],
	}


def _fetch_fpl_league_entries(league_id: int = FPL_CLASSIC_LEAGUE_ID) -> tuple[list[dict], str, str | None]:
	return cache.get_or_set(
		f'fpl:league_entries:{league_id}',
		lambda: _fetch_fpl_league_entries_live(league_id),
		timeout=FPL_CACHE_TIMEOUT,
	)


def _fetch_league_pages(league_id: int, page_param: str, result_key: str, max_pages: int = 200) -> tuple[list[dict], dict]:
	base_url = f'https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/'
	page = 1
	rows: list[dict] = []
	first_payload: dict = {}
	while page <= max_pages:
		params = {'page_standings': 1, 'page_new_entries': 1, page_param: page}
		url = base_url + '?' + '&'.join(f'{key}={value}' for key, value in params.items())
		payload = _get_json(url)
		if page == 1:
			first_payload = payload
		section = payload.get(result_key, {})
		rows.extend(section.get('results', []))
		if not section.get('has_next'):
			break
		page += 1
	return rows, first_payload


def _fetch_league_entry_rows(league_id: int) -> tuple[list[dict], bool]:
	"""Returns (rows, using_new_entries). Falls back to newly-joined entries
	when the league hasn't produced scored standings yet (e.g. pre-season)."""
	standings, _ = _fetch_league_pages(league_id, 'page_standings', 'standings')
	if standings:
		return standings, False
	new_entries, _ = _fetch_league_pages(league_id, 'page_new_entries', 'new_entries')
	return new_entries, True


def _fetch_fpl_league_entries_live(league_id: int = FPL_CLASSIC_LEAGUE_ID) -> tuple[list[dict], str, str | None]:
	try:
		standings_raw, first_payload = _fetch_league_pages(league_id, 'page_standings', 'standings')
		league_name = first_payload.get('league', {}).get('name', f'FPL League {league_id}')

		rows = []
		for index, item in enumerate(standings_raw, start=1):
			manager_name = item.get('player_name', '').strip() or 'Unknown Manager'
			rows.append(
				{
					'rank': item.get('rank') or index,
					'manager_name': manager_name,
					'team_name': item.get('entry_name', 'Unknown Team'),
					'total_points': item.get('total', 0),
					'gameweek_points': item.get('event_total', 0),
				}
			)

		if rows:
			return rows, league_name, None

		new_entries_raw, _ = _fetch_league_pages(league_id, 'page_new_entries', 'new_entries')
		for index, item in enumerate(new_entries_raw, start=1):
			full_name = f"{item.get('player_first_name', '')} {item.get('player_last_name', '')}".strip()
			rows.append(
				{
					'rank': index,
					'manager_name': full_name or 'New Manager',
					'team_name': item.get('entry_name', 'Unknown Team'),
					'total_points': 0,
					'gameweek_points': 0,
				}
			)

		message = None if rows else 'League fetched, but no members were returned yet.'
		return rows, league_name, message
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return [], f'FPL League {league_id}', 'Live league data unavailable. Showing local data.'


def _fetch_captain_leaderboard(league_id: int = FPL_CLASSIC_LEAGUE_ID) -> tuple[list[dict], str, str | None]:
	return cache.get_or_set(
		f'fpl:captain_leaderboard:{league_id}',
		lambda: _fetch_captain_leaderboard_live(league_id),
		timeout=FPL_CACHE_TIMEOUT,
	)


def _fetch_captain_leaderboard_live(league_id: int = FPL_CLASSIC_LEAGUE_ID) -> tuple[list[dict], str, str | None]:
	"""Season-long Captain Mode leaderboard: only each manager's captain's
	points count, added up across every gameweek played so far. Finished
	gameweeks are read straight from CaptainGameweekScore (populated by the
	sync_fpl_data management command) rather than re-fetched here - only the
	CURRENTLY in-progress gameweek (if any) is fetched live, concurrently
	across managers, and added on top of the stored season total."""
	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		current_gameweek = current_event.get('id') if current_event else None
		next_gameweek = next_event.get('id') if next_event else None
		latest_finished_gameweek = (
			CaptainGameweekScore.objects.order_by('-gameweek').values_list('gameweek', flat=True).first()
		)

		if current_gameweek:
			status_label = f'Live - GW{current_gameweek} in progress'
		elif latest_finished_gameweek:
			status_label = f'Season total - through GW{latest_finished_gameweek}'
		elif next_gameweek:
			status_label = f'Season total - GW{next_gameweek} starts soon'
		else:
			status_label = 'Season total'

		entry_rows, using_new_entries = _fetch_league_entry_rows(league_id)
		if not entry_rows:
			return [], status_label, 'League fetched, but no members were returned yet.'

		managers: dict[int, dict] = {}
		for row in entry_rows:
			entry_id = row.get('entry')
			if not entry_id:
				continue
			if using_new_entries:
				manager_name = f"{row.get('player_first_name', '')} {row.get('player_last_name', '')}".strip() or 'New Manager'
			else:
				manager_name = row.get('player_name', '').strip() or 'Unknown Manager'
			managers[entry_id] = {
				'entry_id': entry_id,
				'manager_name': manager_name,
				'team_name': row.get('entry_name', 'Unknown Team'),
				'captain_name': '-',
				'captain_points': 0,
			}

		# Season total from already-finished gameweeks (fast DB read, no API calls).
		stored_totals = (
			CaptainGameweekScore.objects.filter(entry_id__in=managers.keys())
			.values('entry_id')
			.annotate(total=Sum('captain_points'))
		)
		for row in stored_totals:
			if row['entry_id'] in managers:
				managers[row['entry_id']]['captain_points'] += row['total'] or 0

		# Most recent finished gameweek's captain, just for display context.
		# (SQLite has no DISTINCT ON, so just walk gameweeks ascending and
		# let each later row overwrite the previous - last write wins.)
		if managers:
			captain_history = (
				CaptainGameweekScore.objects.filter(entry_id__in=managers.keys())
				.order_by('gameweek')
				.values_list('entry_id', 'captain_name')
			)
			for entry_id, name in captain_history:
				if name and name != '-' and entry_id in managers:
					managers[entry_id]['captain_name'] = name

		# Add the currently in-progress gameweek's live points on top, if any.
		if current_gameweek:
			player_name_lookup = {el['id']: el.get('web_name', 'Unknown') for el in bootstrap.get('elements', [])}
			live_points_by_player: dict[int, int] = {}
			try:
				live_payload = _get_json(f'https://fantasy.premierleague.com/api/event/{current_gameweek}/live/')
				for element in live_payload.get('elements', []):
					live_points_by_player[element.get('id')] = element.get('stats', {}).get('total_points', 0)
			except (error.HTTPError, error.URLError, ValueError, TimeoutError):
				live_points_by_player = {}

			def fetch_one(entry_id: int) -> tuple[int, str, int] | None:
				try:
					picks_payload = _get_json(
						f'https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_gameweek}/picks/'
					)
					captain_pick = next((pick for pick in picks_payload.get('picks', []) if pick.get('is_captain')), None)
					if not captain_pick:
						return None
					element_id = captain_pick.get('element')
					multiplier = captain_pick.get('multiplier') or 2
					points = live_points_by_player.get(element_id, 0) * multiplier
					name = player_name_lookup.get(element_id, 'Unknown')
					return entry_id, name, points
				except (error.HTTPError, error.URLError, ValueError, TimeoutError):
					return None

			with ThreadPoolExecutor(max_workers=15) as executor:
				futures = [executor.submit(fetch_one, entry_id) for entry_id in managers]
				for future in as_completed(futures):
					result = future.result()
					if result:
						entry_id, captain_name, points = result
						managers[entry_id]['captain_points'] += points
						managers[entry_id]['captain_name'] = captain_name

		leaderboard = list(managers.values())
		leaderboard.sort(key=lambda row: row['captain_points'], reverse=True)
		for index, row in enumerate(leaderboard, start=1):
			row['rank'] = index

		return leaderboard, status_label, None
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return [], 'Season total', 'Captain leaderboard temporarily unavailable.'


def _is_season_finished() -> bool:
	return cache.get_or_set('fpl:season_finished', _is_season_finished_live, timeout=3600)


def _is_season_finished_live() -> bool:
	"""True only once the LAST gameweek of the season has finished. Used to
	keep season-long results (the Classic League winner, the Captain Mode
	season leaderboard winner) anonymous while still in progress - only
	the per-gameweek and per-month results are final early, since those
	have their own natural end point."""
	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		events = bootstrap.get('events', [])
		if not events:
			return False
		last_event = max(events, key=lambda event: event['id'])
		return bool(last_event.get('finished'))
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return False


def _resolved_league_dataset() -> tuple[list[dict], str, str | None, str]:
	live_rows, league_name, live_error = _fetch_fpl_league_entries()
	if live_rows:
		return live_rows, league_name, live_error, 'live'

	return [], league_name, live_error or 'No league data available.', 'none'


def _fetch_gameweek_leaderboard(
	league_id: int = FPL_CLASSIC_LEAGUE_ID, selected_gameweek: int | None = None
) -> dict:
	return cache.get_or_set(
		f'fpl:gameweek_leaderboard:{league_id}:{selected_gameweek or "latest"}',
		lambda: _fetch_gameweek_leaderboard_live(league_id, selected_gameweek),
		timeout=300,
	)


def _fetch_gameweek_leaderboard_live(
	league_id: int = FPL_CLASSIC_LEAGUE_ID, selected_gameweek: int | None = None
) -> dict:
	"""Gameweek Winners: each manager's points for one specific gameweek,
	picked via a dropdown, plus their cumulative total through that
	gameweek. Finished gameweeks are read straight from
	CaptainGameweekScore; the currently in-progress gameweek (if selected)
	is fetched live, same pattern as Captain Mode and Manager of the
	Month."""
	empty = {
		'entries': [],
		'winner': None,
		'available_gameweeks': [],
		'selected_gameweek': None,
		'selected_gameweek_finished': False,
		'gameweek_error': None,
	}
	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		current_gameweek = current_event.get('id') if current_event else None

		# Kept separate from available_gameweeks below (which also includes
		# the current/next gameweek purely so there's something selectable) -
		# this is the set that actually determines whether a winner can be
		# revealed yet.
		truly_finished_gameweeks = {event['id'] for event in events if event.get('finished')}
		finished_gameweeks = set(truly_finished_gameweeks)
		reference_gameweek = current_gameweek or (next_event.get('id') if next_event else None)
		if reference_gameweek:
			finished_gameweeks.add(reference_gameweek)
		available_gameweeks = sorted(finished_gameweeks)

		if not available_gameweeks:
			return {**empty, 'gameweek_error': 'Could not determine any gameweeks from the FPL API.'}

		try:
			selected_gameweek = int(selected_gameweek)
		except (TypeError, ValueError):
			selected_gameweek = None
		if selected_gameweek not in available_gameweeks:
			selected_gameweek = available_gameweeks[-1]
		selected_gameweek_finished = selected_gameweek in truly_finished_gameweeks

		entry_rows, using_new_entries = _fetch_league_entry_rows(league_id)
		if not entry_rows:
			return {
				**empty,
				'available_gameweeks': [{'value': gw, 'label': f'Gameweek {gw}'} for gw in available_gameweeks],
				'selected_gameweek': selected_gameweek,
				'selected_gameweek_finished': selected_gameweek_finished,
				'gameweek_error': 'League fetched, but no members were returned yet.',
			}

		managers: dict[int, dict] = {}
		for row in entry_rows:
			entry_id = row.get('entry')
			if not entry_id:
				continue
			if using_new_entries:
				manager_name = f"{row.get('player_first_name', '')} {row.get('player_last_name', '')}".strip() or 'New Manager'
			else:
				manager_name = row.get('player_name', '').strip() or 'Unknown Manager'
			managers[entry_id] = {
				'entry_id': entry_id,
				'manager_name': manager_name,
				'team_name': row.get('entry_name', 'Unknown Team'),
				'gameweek_points': 0,
				'total_points': 0,
			}

		# Cumulative total through the selected gameweek, from stored finished weeks.
		cumulative = (
			CaptainGameweekScore.objects.filter(entry_id__in=managers.keys(), gameweek__lte=selected_gameweek)
			.values('entry_id')
			.annotate(total=Sum('gameweek_points'))
		)
		for row in cumulative:
			if row['entry_id'] in managers:
				managers[row['entry_id']]['total_points'] = row['total'] or 0

		if selected_gameweek == current_gameweek:
			def fetch_one(entry_id: int) -> tuple[int, int] | None:
				try:
					picks_payload = _get_json(
						f'https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_gameweek}/picks/'
					)
					return entry_id, picks_payload.get('entry_history', {}).get('points', 0)
				except (error.HTTPError, error.URLError, ValueError, TimeoutError):
					return None

			with ThreadPoolExecutor(max_workers=15) as executor:
				futures = [executor.submit(fetch_one, entry_id) for entry_id in managers]
				for future in as_completed(futures):
					result = future.result()
					if result:
						entry_id, points = result
						managers[entry_id]['gameweek_points'] = points
						managers[entry_id]['total_points'] += points
		else:
			this_gw = CaptainGameweekScore.objects.filter(
				entry_id__in=managers.keys(), gameweek=selected_gameweek
			).values_list('entry_id', 'gameweek_points')
			for entry_id, points in this_gw:
				if entry_id in managers:
					managers[entry_id]['gameweek_points'] = points

		entries = list(managers.values())
		entries.sort(key=lambda row: row['gameweek_points'], reverse=True)
		for index, row in enumerate(entries, start=1):
			row['rank'] = index

		return {
			'entries': entries[:15],
			'winner': entries[0] if selected_gameweek_finished and entries else None,
			'available_gameweeks': [{'value': gw, 'label': f'Gameweek {gw}'} for gw in available_gameweeks],
			'selected_gameweek': selected_gameweek,
			'selected_gameweek_finished': selected_gameweek_finished,
			'gameweek_error': None,
		}
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return {**empty, 'gameweek_error': 'Gameweek leaderboard temporarily unavailable.'}


def _month_label(year_month: str) -> str:
	return datetime.strptime(year_month, '%Y-%m').strftime('%B %Y')


def _gameweek_month_map(events: list[dict]) -> dict[int, str]:
	month_map = {}
	for event in events:
		deadline = event.get('deadline_time')
		if deadline:
			dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
			month_map[event['id']] = dt.strftime('%Y-%m')
	return month_map


def _fetch_monthly_leaderboard(
	league_id: int = FPL_CLASSIC_LEAGUE_ID, selected_month: str | None = None
) -> dict:
	return cache.get_or_set(
		f'fpl:monthly_leaderboard:{league_id}:{selected_month or "latest"}',
		lambda: _fetch_monthly_leaderboard_live(league_id, selected_month),
		timeout=FPL_CACHE_TIMEOUT,
	)


def _fetch_monthly_leaderboard_live(
	league_id: int = FPL_CLASSIC_LEAGUE_ID, selected_month: str | None = None
) -> dict:
	"""Manager of the Month: Sigma (gameweek points - transfer hit cost) for
	only the gameweeks whose deadline falls in the chosen calendar month.
	Finished gameweeks are read straight from CaptainGameweekScore
	(populated by sync_fpl_data), net of whatever hit cost was stored for
	that gameweek; if the currently in-progress gameweek falls in the
	selected month, its points are fetched live and added on top net of
	that gameweek's hit cost too, same pattern as the season-long Captain
	Mode leaderboard."""
	empty = {
		'monthly_rankings': [],
		'monthly_winner': None,
		'available_months': [],
		'selected_month': None,
		'selected_month_label': None,
		'selected_month_finished': False,
		'monthly_error': None,
	}
	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		events = bootstrap.get('events', [])
		current_event = next((event for event in events if event.get('is_current')), None)
		next_event = next((event for event in events if event.get('is_next')), None)
		current_gameweek = current_event.get('id') if current_event else None

		gameweek_month_map = _gameweek_month_map(events)

		stored_gameweeks = CaptainGameweekScore.objects.values_list('gameweek', flat=True).distinct()
		months_with_data = {gameweek_month_map[gw] for gw in stored_gameweeks if gw in gameweek_month_map}

		# Always include the current-or-next gameweek's month too, so there's
		# a sensible month to land on before any month has finished.
		reference_gameweek = current_gameweek or (next_event.get('id') if next_event else None)
		reference_month = gameweek_month_map.get(reference_gameweek) if reference_gameweek else None
		if reference_month:
			months_with_data.add(reference_month)

		available_months = sorted(months_with_data)
		if not available_months:
			return {**empty, 'monthly_error': 'Could not determine any gameweek months from the FPL API.'}

		if selected_month not in available_months:
			selected_month = available_months[-1]

		gameweeks_in_month = [gw for gw, month in gameweek_month_map.items() if month == selected_month]
		# A month is only "finished" once every gameweek whose deadline falls
		# in it is actually marked finished by the FPL API - not just "not
		# currently in progress", since pre-season there's no current
		# gameweek at all (GW1 is only 'next' until its deadline passes),
		# which would otherwise make an unstarted month look finished.
		truly_finished_gameweek_ids = {event['id'] for event in events if event.get('finished')}
		selected_month_finished = bool(gameweeks_in_month) and all(
			gw in truly_finished_gameweek_ids for gw in gameweeks_in_month
		)

		entry_rows, using_new_entries = _fetch_league_entry_rows(league_id)
		if not entry_rows:
			return {
				**empty,
				'available_months': [{'value': m, 'label': _month_label(m)} for m in available_months],
				'selected_month': selected_month,
				'selected_month_label': _month_label(selected_month),
				'selected_month_finished': selected_month_finished,
				'monthly_error': 'League fetched, but no members were returned yet.',
			}

		managers: dict[int, dict] = {}
		for index, row in enumerate(entry_rows, start=1):
			entry_id = row.get('entry')
			if not entry_id:
				continue
			if using_new_entries:
				manager_name = f"{row.get('player_first_name', '')} {row.get('player_last_name', '')}".strip() or 'New Manager'
				league_rank = index
			else:
				manager_name = row.get('player_name', '').strip() or 'Unknown Manager'
				league_rank = row.get('rank') or index
			managers[entry_id] = {
				'entry_id': entry_id,
				'manager_name': manager_name,
				'team_name': row.get('entry_name', 'Unknown Team'),
				'league_rank': league_rank,
				'monthly_points': 0,
				'monthly_hits': 0,
			}

		stored_sums = (
			CaptainGameweekScore.objects.filter(entry_id__in=managers.keys(), gameweek__in=gameweeks_in_month)
			.values('entry_id')
			.annotate(
				net_total=Sum(F('gameweek_points') - F('event_transfers_cost')),
				hits_total=Sum('event_transfers_cost'),
			)
		)
		for row in stored_sums:
			if row['entry_id'] in managers:
				managers[row['entry_id']]['monthly_points'] += row['net_total'] or 0
				managers[row['entry_id']]['monthly_hits'] += row['hits_total'] or 0

		if current_gameweek and gameweek_month_map.get(current_gameweek) == selected_month:
			def fetch_one(entry_id: int) -> tuple[int, int, int] | None:
				try:
					picks_payload = _get_json(
						f'https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_gameweek}/picks/'
					)
					entry_history = picks_payload.get('entry_history', {})
					return entry_id, entry_history.get('points', 0), entry_history.get('event_transfers_cost', 0)
				except (error.HTTPError, error.URLError, ValueError, TimeoutError):
					return None

			with ThreadPoolExecutor(max_workers=15) as executor:
				futures = [executor.submit(fetch_one, entry_id) for entry_id in managers]
				for future in as_completed(futures):
					result = future.result()
					if result:
						entry_id, points, hits = result
						managers[entry_id]['monthly_points'] += points - hits
						managers[entry_id]['monthly_hits'] += hits

		leaderboard = list(managers.values())
		leaderboard.sort(key=lambda row: row['monthly_points'], reverse=True)
		for index, row in enumerate(leaderboard, start=1):
			row['rank'] = index

		return {
			'monthly_rankings': leaderboard[:15],
			'monthly_winner': leaderboard[0] if selected_month_finished and leaderboard else None,
			'available_months': [{'value': m, 'label': _month_label(m)} for m in available_months],
			'selected_month': selected_month,
			'selected_month_label': _month_label(selected_month),
			'selected_month_finished': selected_month_finished,
			'monthly_error': None,
		}
	except (error.HTTPError, error.URLError, ValueError, KeyError, TypeError, TimeoutError):
		return {**empty, 'monthly_error': 'Monthly leaderboard temporarily unavailable.'}


def _build_classic_data(rows: list[dict]) -> dict:
	sorted_rows = sorted(rows, key=lambda row: row['rank'])
	leader_points = sorted_rows[0]['total_points'] if sorted_rows else 0
	classic_rows = []
	for row in sorted_rows:
		gap = leader_points - row['total_points']
		form = 'Hot' if row['gameweek_points'] >= 70 else 'Steady' if row['gameweek_points'] >= 60 else 'Cold'
		classic_rows.append(
			{
				'rank': row['rank'],
				'manager_name': row['manager_name'],
				'team_name': row['team_name'],
				'total_points': row['total_points'],
				'gap_to_leader': gap,
				'form': form,
			}
		)

	return {
		'leader_points': leader_points,
		'classic_rows': classic_rows,
	}


def _page_ad(page: str) -> PageAdvertisement | None:
	"""Each page's ad slot, edited independently in the admin. Rows are
	seeded per Page choice by migration 0009, but fall back to None (no ad
	shown) if a row is somehow missing rather than erroring the page."""
	return PageAdvertisement.objects.filter(page=page).first()


def _archive_current_season(season: Season, league_id: int = FPL_CLASSIC_LEAGUE_ID) -> dict:
	"""Snapshots final standings, every gameweek/monthly winner, and the
	season captain leaderboard into the given (already-created, empty)
	Season row, using the exact same live computations the public pages
	use, so the archive matches what was actually shown. Meant to be run
	once, manually, after a season is genuinely over - CaptainGameweekScore
	and LeagueEntry get overwritten by sync_fpl_data once next season's
	gameweeks start, so this is the one chance to freeze the numbers."""
	summary = {'standings': 0, 'gameweek_winners': 0, 'monthly_winners': 0, 'captain_standings': 0}

	rows, league_name, _league_error, _league_source = _resolved_league_dataset()
	if league_name and not season.league_name:
		season.league_name = league_name
		season.save(update_fields=['league_name'])

	standings = [
		SeasonStanding(
			season=season,
			rank=row['rank'],
			manager_name=row['manager_name'],
			team_name=row['team_name'],
			total_points=row['total_points'],
		)
		for row in rows
	]
	SeasonStanding.objects.bulk_create(standings)
	summary['standings'] = len(standings)

	finished_gameweeks = sorted(CaptainGameweekScore.objects.values_list('gameweek', flat=True).distinct())
	gameweek_winner_rows = []
	for gameweek in finished_gameweeks:
		gameweek_data = _fetch_gameweek_leaderboard_live(league_id, selected_gameweek=gameweek)
		winner = gameweek_data.get('winner')
		if winner:
			gameweek_winner_rows.append(
				SeasonGameweekWinner(
					season=season,
					gameweek=gameweek,
					manager_name=winner['manager_name'],
					team_name=winner['team_name'],
					points=winner['gameweek_points'],
				)
			)
	SeasonGameweekWinner.objects.bulk_create(gameweek_winner_rows)
	summary['gameweek_winners'] = len(gameweek_winner_rows)

	try:
		bootstrap = _get_json('https://fantasy.premierleague.com/api/bootstrap-static/')
		events = bootstrap.get('events', [])
	except (error.HTTPError, error.URLError, ValueError, TimeoutError):
		events = []
	gameweek_month_map = _gameweek_month_map(events)
	months = sorted({gameweek_month_map[gw] for gw in finished_gameweeks if gw in gameweek_month_map})
	monthly_winner_rows = []
	for month in months:
		month_data = _fetch_monthly_leaderboard_live(league_id, selected_month=month)
		winner = month_data.get('monthly_winner')
		if winner:
			monthly_winner_rows.append(
				SeasonMonthlyWinner(
					season=season,
					month_label=month_data.get('selected_month_label') or _month_label(month),
					manager_name=winner['manager_name'],
					team_name=winner['team_name'],
					points=winner['monthly_points'],
				)
			)
	SeasonMonthlyWinner.objects.bulk_create(monthly_winner_rows)
	summary['monthly_winners'] = len(monthly_winner_rows)

	captain_rows, _status_label, _captain_error = _fetch_captain_leaderboard_live(league_id)
	captain_standing_rows = [
		SeasonCaptainStanding(
			season=season,
			rank=row['rank'],
			manager_name=row['manager_name'],
			team_name=row['team_name'],
			captain_points=row['captain_points'],
		)
		for row in captain_rows
	]
	SeasonCaptainStanding.objects.bulk_create(captain_standing_rows)
	summary['captain_standings'] = len(captain_standing_rows)

	return summary


def home(request):
	base_context = _base_page_context('home')
	dashboard_data = _fetch_dashboard_data()
	rows, _, _, _ = _resolved_league_dataset()
	context = {
		**base_context,
		**dashboard_data,
		'standings': rows[:5],
	}
	return render(request, 'fantasy/home.html', context)


def live_gameweek(request):
	entry_id_raw = request.GET.get('entry_id', '').strip()
	player_id_raw = request.GET.get('player_id', '').strip()
	if not entry_id_raw:
		entry_id_raw = str(request.session.get('fpl_entry_id', '')).strip()
	base_context = _base_page_context('live_gameweek')
	context = {
		**base_context,
		'entry_id': entry_id_raw,
		'player_id': player_id_raw,
		'live_data': None,
		'entry_history': None,
		'player_history': None,
		'error_message': None,
		'entry_history_error': None,
		'player_error': None,
		'saved_message': None,
	}

	if entry_id_raw:
		if not entry_id_raw.isdigit():
			context['error_message'] = 'FPL ID should contain numbers only.'
		else:
			entry_history, entry_history_error = _fetch_entry_history(int(entry_id_raw))
			context['entry_history'] = entry_history
			context['entry_history_error'] = entry_history_error

			live_data, error_message = _fetch_fpl_live_data(int(entry_id_raw))
			context['live_data'] = live_data
			context['error_message'] = error_message
			if live_data:
				request.session['fpl_entry_id'] = int(entry_id_raw)
				context['saved_message'] = 'Team added successfully. It will load automatically next time.'

	if player_id_raw:
		if not player_id_raw.isdigit():
			context['player_error'] = 'Player ID should contain numbers only.'
		else:
			player_history, player_error = _fetch_player_history(int(player_id_raw))
			context['player_history'] = player_history
			context['player_error'] = player_error

	return render(request, 'fantasy/live_gameweek.html', context)


def captain_mode(request):
	entry_id_raw = request.GET.get('entry_id', '').strip()
	if not entry_id_raw:
		entry_id_raw = str(request.session.get('fpl_entry_id', '')).strip()

	base_context = _base_page_context('captain_mode')
	captain_leaderboard, leaderboard_status, leaderboard_error = _fetch_captain_leaderboard()
	_rows, league_name, _league_error, _league_source = _resolved_league_dataset()
	season_finished = _is_season_finished()
	captain_season_winner = captain_leaderboard[0] if season_finished and captain_leaderboard else None
	context = {
		**base_context,
		'entry_id': entry_id_raw,
		'captain_data': None,
		'captain_error': None,
		'saved_message': None,
		'captain_leaderboard': captain_leaderboard,
		'leaderboard_status': leaderboard_status,
		'leaderboard_error': leaderboard_error,
		'league_name': league_name,
		'page_ad': _page_ad(PageAdvertisement.Page.CAPTAIN_MODE),
		'season_finished': season_finished,
		'captain_season_winner': captain_season_winner,
	}

	if entry_id_raw:
		if not entry_id_raw.isdigit():
			context['captain_error'] = 'FPL ID should contain numbers only.'
		else:
			captain_data, captain_error = _build_captain_recommendations(int(entry_id_raw))
			context['captain_data'] = captain_data
			context['captain_error'] = captain_error
			if captain_data:
				request.session['fpl_entry_id'] = int(entry_id_raw)
				context['saved_message'] = 'Captain mode loaded. This FPL ID is now saved for quick access.'

	return render(request, 'fantasy/captain_mode.html', context)


def gameweek_winners(request):
	base_context = _base_page_context('gameweek_winners')
	selected_gameweek = request.GET.get('gameweek', '').strip() or None
	gameweek_data = _fetch_gameweek_leaderboard(selected_gameweek=selected_gameweek)
	_rows, league_name, league_error, league_source = _resolved_league_dataset()
	context = {
		**base_context,
		**gameweek_data,
		'league_name': league_name,
		'league_error': league_error,
		'league_source': league_source,
		'page_ad': _page_ad(PageAdvertisement.Page.GAMEWEEK_WINNERS),
	}
	return render(request, 'fantasy/gameweek_winners.html', context)


def manager_of_the_month(request):
	base_context = _base_page_context('manager_of_the_month')
	selected_month = request.GET.get('month', '').strip() or None
	monthly_data = _fetch_monthly_leaderboard(selected_month=selected_month)
	_rows, league_name, _league_error, _league_source = _resolved_league_dataset()
	context = {
		**base_context,
		**monthly_data,
		'league_name': league_name,
		'page_ad': _page_ad(PageAdvertisement.Page.MANAGER_OF_THE_MONTH),
	}
	return render(request, 'fantasy/manager_of_the_month.html', context)


def classic_league(request):
	base_context = _base_page_context('classic_league')
	rows, league_name, league_error, league_source = _resolved_league_dataset()
	classic_data = _build_classic_data(rows)
	season_finished = _is_season_finished()
	classic_rows = classic_data.get('classic_rows') or []
	classic_season_winner = classic_rows[0] if season_finished and classic_rows else None
	context = {
		**base_context,
		**classic_data,
		'league_name': league_name,
		'league_error': league_error,
		'league_source': league_source,
		'page_ad': _page_ad(PageAdvertisement.Page.CLASSIC_LEAGUE),
		'season_finished': season_finished,
		'classic_season_winner': classic_season_winner,
	}
	return render(request, 'fantasy/classic_league.html', context)


def league_live_data(request):
	rows, league_name, league_error, league_source = _resolved_league_dataset()
	classic_data = _build_classic_data(rows)
	selected_gameweek = request.GET.get('gameweek', '').strip() or None
	gameweek_data = _fetch_gameweek_leaderboard(selected_gameweek=selected_gameweek)
	selected_month = request.GET.get('month', '').strip() or None
	monthly_data = _fetch_monthly_leaderboard(selected_month=selected_month)

	response = {
		'league_name': league_name,
		'league_error': league_error,
		'league_source': league_source,
		'classic': {
			'leader_points': classic_data['leader_points'],
			'rows': classic_data['classic_rows'],
		},
		'gameweek': {
			'winner': gameweek_data['winner'],
			'entries': gameweek_data['entries'],
			'selected_gameweek': gameweek_data['selected_gameweek'],
			'selected_gameweek_finished': gameweek_data['selected_gameweek_finished'],
		},
		'monthly': {
			'winner': monthly_data['monthly_winner'],
			'rankings': monthly_data['monthly_rankings'],
			'selected_month': monthly_data['selected_month'],
			'selected_month_label': monthly_data['selected_month_label'],
			'selected_month_finished': monthly_data['selected_month_finished'],
		},
	}
	return JsonResponse(response)


def past_seasons(request):
	base_context = _base_page_context('past_seasons')
	context = {
		**base_context,
		'seasons': Season.objects.all(),
	}
	return render(request, 'fantasy/past_seasons.html', context)


def season_detail(request, season_id):
	base_context = _base_page_context('past_seasons')
	season = get_object_or_404(Season, pk=season_id)
	context = {
		**base_context,
		'season': season,
		'standings': season.standings.all(),
		'gameweek_winners': season.gameweek_winners.all(),
		'monthly_winners': season.monthly_winners.all(),
		'captain_standings': season.captain_standings.all(),
	}
	return render(request, 'fantasy/season_detail.html', context)
