from django.contrib import admin
from django.contrib.admin import AdminSite
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.urls import path

from .models import CaptainGameweekScore, LeagueEntry, PageAdvertisement, Player, SiteSettings


class FantasyAdminSite(AdminSite):
    site_header = 'FPL Bhaktapur'
    site_title = 'FPL Bhaktapur Admin'
    index_title = 'Manage Top Picks and Mini League Standings'
    index_template = 'admin/fantasy_index.html'
    login_template = 'admin/fantasy_login.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        context = {
            **self.each_context(request),
            'title': 'Quick Stats Dashboard',
            'top_picks': Player.objects.select_related('team').order_by('-selected_by_percent', '-total_points')[:5],
            'league_leaders': LeagueEntry.objects.order_by('rank')[:5],
            'player_count': Player.objects.count(),
            'league_count': LeagueEntry.objects.count(),
        }
        return TemplateResponse(request, 'admin/fantasy_dashboard.html', context)


fantasy_admin_site = FantasyAdminSite(name='fantasy_admin')


class PlayerAdmin(admin.ModelAdmin):
	list_display = (
		'name',
		'team',
		'position',
		'price',
		'total_points',
		'goals',
		'assists',
		'clean_sheets',
		'selected_by_percent',
		'is_top_pick',
	)
	list_filter = ('position', 'team')
	search_fields = ('name', 'team__name', 'team__short_name')
	ordering = ('-selected_by_percent', '-total_points', 'name')
	list_per_page = 25
	fieldsets = (
		('Player Profile', {'fields': ('name', 'team', 'position', 'photo_url')}),
		('Top Picks Metrics', {'fields': ('price', 'total_points', 'selected_by_percent')}),
		('Top Stats Metrics', {'fields': ('goals', 'assists', 'clean_sheets')}),
	)

	@admin.display(boolean=True, description='Top Pick')
	def is_top_pick(self, obj):
		return obj.selected_by_percent >= 15


class LeagueEntryAdmin(admin.ModelAdmin):
	list_display = ('rank', 'manager_name', 'team_name', 'total_points', 'gameweek_points')
	list_filter = ('rank',)
	search_fields = ('manager_name', 'team_name')
	ordering = ('rank',)
	list_per_page = 200
	# Points come from the FPL API sync (sync_fpl_data) and are overwritten on
	# every run, so they're shown read-only here rather than editable - manual
	# edits would just be silently lost on the next sync anyway.
	readonly_fields = ('total_points', 'gameweek_points')
	fieldsets = (
		('League Ranking', {'fields': ('rank',)}),
		('Manager Details', {'fields': ('manager_name', 'team_name')}),
		('Points (synced from the FPL API)', {'fields': ('gameweek_points', 'total_points')}),
	)


class PageAdvertisementAdmin(admin.ModelAdmin):
	list_display = ('page', 'image', 'link_url', 'updated_at')
	list_display_links = ('page',)
	readonly_fields = ('page', 'updated_at')
	fieldsets = (
		(None, {'fields': ('page',)}),
		('Advertisement', {
			'fields': ('image', 'link_url', 'alt_text', 'caption', 'updated_at'),
			'description': 'Shown in the right half of this page\'s league banner. Leave the image blank to show no ad on this page.',
		}),
		('Social links', {
			'fields': ('instagram_url', 'facebook_url'),
			'description': 'Optional - shown as small icons under the ad image when set.',
		}),
	)

	# Exactly one row per Page choice, seeded by migration 0008 - never
	# add/delete here, only edit the image/link on the existing rows.
	def has_add_permission(self, request):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


class SiteSettingsAdmin(admin.ModelAdmin):
	fieldsets = (
		('Logo', {'fields': ('logo', 'updated_at'), 'description': 'Upload once - it appears in the sidebar across the whole site and this admin.'}),
	)
	readonly_fields = ('updated_at',)

	def has_add_permission(self, request):
		# Singleton: only ever one row (pk=1), created on demand.
		return not SiteSettings.objects.exists()

	def has_delete_permission(self, request, obj=None):
		return False

	def changelist_view(self, request, extra_context=None):
		# Skip straight to the single settings row instead of showing a list.
		obj = SiteSettings.load()
		return redirect('fantasy_admin:fantasy_sitesettings_change', obj.pk)


class CaptainGameweekScoreAdmin(admin.ModelAdmin):
	list_display = ('gameweek', 'manager_name', 'team_name', 'gameweek_points', 'event_transfers_cost', 'captain_name', 'captain_points')
	list_filter = ('gameweek',)
	search_fields = ('manager_name', 'team_name', 'captain_name')
	ordering = ('-gameweek', '-captain_points')
	list_per_page = 200
	# Backfilled by sync_fpl_data for finished gameweeks only - editing here
	# would just be overwritten (or ignored, since finished weeks are never
	# re-fetched) on the next sync.
	readonly_fields = ('entry_id', 'manager_name', 'team_name', 'gameweek', 'gameweek_points', 'event_transfers_cost', 'captain_name', 'captain_points')

	def has_add_permission(self, request):
		return False


fantasy_admin_site.register(Player, PlayerAdmin)
fantasy_admin_site.register(LeagueEntry, LeagueEntryAdmin)
fantasy_admin_site.register(SiteSettings, SiteSettingsAdmin)
fantasy_admin_site.register(CaptainGameweekScore, CaptainGameweekScoreAdmin)
fantasy_admin_site.register(PageAdvertisement, PageAdvertisementAdmin)
