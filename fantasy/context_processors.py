import os

from django.contrib.staticfiles import finders

from .models import SiteSettings


def site_branding(request):
	settings_obj = SiteSettings.load()
	return {
		'site_logo_url': settings_obj.logo.url if settings_obj.logo else None,
		'captain_leaderboard_note': settings_obj.captain_leaderboard_note,
		'captain_recommendation_note': settings_obj.captain_recommendation_note,
		'monthly_winner_note': settings_obj.monthly_winner_note,
	}


def saved_team(request):
	"""The "Your Team" chip shown site-wide once a manager has entered
	their FPL ID on the Live Tracker page (fpl_entry_id saved to their
	session there) - lets every other page link straight back to their
	own team instead of that only being reachable from live_gameweek."""
	entry_id = request.session.get('fpl_entry_id')
	if not entry_id:
		return {'saved_team': None}
	from .views import _fetch_saved_team_summary

	try:
		return {'saved_team': _fetch_saved_team_summary(int(entry_id))}
	except (TypeError, ValueError):
		return {'saved_team': None}


def _mtime_version(static_path: str) -> int:
	try:
		path = finders.find(static_path)
		return int(os.path.getmtime(path)) if path else 0
	except (OSError, ValueError, TypeError):
		return 0


def static_version(request):
	"""Cache-busting query params for the public site's and admin's CSS/JS,
	derived from each source file's own mtime instead of a hand-maintained
	literal - a forgotten manual bump previously left browsers serving
	stale CSS/JS after a deploy. finders.find() resolves the source file in
	both dev (STATICFILES_DIRS) and production (same source tree,
	independent of whether collectstatic has run), so this works without
	extra setup.

	static_version is shared by both style.css and app.js in base.html, so
	it has to be the max of both files' mtimes - using only one file's
	mtime meant an edit to the other never busted the cache."""
	return {
		'static_version': max(_mtime_version('fantasy/css/style.css'), _mtime_version('fantasy/js/app.js')),
		'admin_static_version': _mtime_version('fantasy/css/admin_theme.css'),
	}
