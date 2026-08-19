from django.contrib import admin, messages
from django.contrib.admin import AdminSite
from django.db import models
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.urls import path

from .models import (
	CaptainGameweekScore,
	LeagueEntry,
	PageAdvertisement,
	Player,
	Season,
	SeasonCaptainStanding,
	SeasonGameweekWinner,
	SeasonMonthlyWinner,
	SeasonStanding,
	SiteSettings,
)
from .views import _archive_current_season


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
		(
			'Explanation text',
			{
				'fields': ('captain_leaderboard_note', 'captain_recommendation_note', 'monthly_winner_note'),
				'description': 'The "How this is chosen" notes shown on Captain Mode and Manager of the Month. Basic HTML is allowed.',
			},
		),
	)
	readonly_fields = ('updated_at',)
	formfield_overrides = {
		models.TextField: {'widget': admin.widgets.AdminTextareaWidget(attrs={'rows': 6, 'style': 'width: 100%; max-width: 640px;'})},
	}

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
	list_editable = ('gameweek_points', 'event_transfers_cost', 'captain_name', 'captain_points')
	list_filter = ('gameweek',)
	search_fields = ('manager_name', 'team_name', 'captain_name')
	ordering = ('-gameweek', '-captain_points')
	list_per_page = 200
	# Backfilled by sync_fpl_data, but only ever for (manager, gameweek)
	# pairs that don't already have a row - so a manual edit or add here is
	# safe and permanent, it will never get silently overwritten by a later
	# sync. This feeds both the Captain Mode season-total leaderboard
	# (captain_points) and the Manager of the Month leaderboard
	# (gameweek_points), so editing a row here updates both.
	fieldsets = (
		('Manager', {'fields': ('entry_id', 'manager_name', 'team_name', 'gameweek')}),
		('Gameweek score (feeds Manager of the Month)', {'fields': ('gameweek_points', 'event_transfers_cost')}),
		('Captain (feeds Captain Mode)', {'fields': ('captain_name', 'captain_points')}),
	)


class SeasonStandingInline(admin.TabularInline):
	model = SeasonStanding
	extra = 0
	can_delete = False
	fields = ('rank', 'manager_name', 'team_name', 'total_points')
	readonly_fields = fields
	verbose_name = 'Final standing'
	verbose_name_plural = 'Final classic league standings'

	def has_add_permission(self, request, obj=None):
		return False


class SeasonCaptainStandingInline(admin.TabularInline):
	model = SeasonCaptainStanding
	extra = 0
	can_delete = False
	fields = ('rank', 'manager_name', 'team_name', 'captain_points')
	readonly_fields = fields
	verbose_name = 'Captain standing'
	verbose_name_plural = 'Final captain leaderboard'

	def has_add_permission(self, request, obj=None):
		return False


class SeasonMonthlyWinnerInline(admin.TabularInline):
	model = SeasonMonthlyWinner
	extra = 0
	can_delete = False
	fields = ('month_label', 'manager_name', 'team_name', 'points')
	readonly_fields = fields
	verbose_name = 'Monthly winner'
	verbose_name_plural = 'Manager of the Month winners'

	def has_add_permission(self, request, obj=None):
		return False


class SeasonGameweekWinnerInline(admin.TabularInline):
	model = SeasonGameweekWinner
	extra = 0
	can_delete = False
	fields = ('gameweek', 'manager_name', 'team_name', 'points')
	readonly_fields = fields
	verbose_name = 'Gameweek winner'
	verbose_name_plural = 'Gameweek winners'

	def has_add_permission(self, request, obj=None):
		return False


class SeasonAdmin(admin.ModelAdmin):
	list_display = ('name', 'league_name', 'archived_at')
	inlines = [SeasonStandingInline, SeasonCaptainStandingInline, SeasonMonthlyWinnerInline, SeasonGameweekWinnerInline]

	def get_fields(self, request, obj=None):
		if obj is None:
			# league_name/archived_at aren't known yet - archiving fills
			# them in right after this row is created.
			return ('name',)
		return ('name', 'league_name', 'archived_at')

	def get_readonly_fields(self, request, obj=None):
		if obj is None:
			return ()
		return ('league_name', 'archived_at')

	def get_inline_instances(self, request, obj=None):
		# No point showing empty inline tables on the "add" form - there's
		# nothing to show until the archive snapshot has actually run.
		if obj is None:
			return []
		return super().get_inline_instances(request, obj)

	def save_model(self, request, obj, form, change):
		super().save_model(request, obj, form, change)
		if not change:
			summary = _archive_current_season(obj)
			self.message_user(
				request,
				(
					f"Archived '{obj.name}': {summary['standings']} final standings, "
					f"{summary['gameweek_winners']} gameweek winners, "
					f"{summary['monthly_winners']} monthly winners, "
					f"{summary['captain_standings']} captain standings."
				),
				level=messages.SUCCESS,
			)


fantasy_admin_site.register(Player, PlayerAdmin)
fantasy_admin_site.register(LeagueEntry, LeagueEntryAdmin)
fantasy_admin_site.register(SiteSettings, SiteSettingsAdmin)
fantasy_admin_site.register(CaptainGameweekScore, CaptainGameweekScoreAdmin)
fantasy_admin_site.register(PageAdvertisement, PageAdvertisementAdmin)
fantasy_admin_site.register(Season, SeasonAdmin)
