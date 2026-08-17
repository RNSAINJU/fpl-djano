import os

from django.contrib.staticfiles import finders

from .models import SiteSettings


def site_branding(request):
	settings_obj = SiteSettings.load()
	return {
		'site_logo_url': settings_obj.logo.url if settings_obj.logo else None,
	}


def static_version(request):
	"""Cache-busting query param for style.css/app.js, derived from the
	source file's own mtime instead of a hand-maintained literal - a
	forgotten manual bump previously left browsers serving stale CSS/JS
	after a deploy. finders.find() resolves the source file in both dev
	(STATICFILES_DIRS) and production (same source tree, independent of
	whether collectstatic has run), so this works without extra setup."""
	try:
		path = finders.find('fantasy/css/style.css')
		version = int(os.path.getmtime(path)) if path else 0
	except (OSError, ValueError, TypeError):
		version = 0
	return {'static_version': version}
