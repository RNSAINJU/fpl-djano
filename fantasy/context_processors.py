from .models import SiteSettings


def site_branding(request):
	settings_obj = SiteSettings.load()
	return {
		'site_logo_url': settings_obj.logo.url if settings_obj.logo else None,
	}
