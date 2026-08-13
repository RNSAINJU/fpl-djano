from django.contrib import admin
from django.contrib.admin import AdminSite
from django.template.response import TemplateResponse
from django.urls import path

from .models import Fixture, LeagueEntry, Player, Team


class FantasyAdminSite(AdminSite):
    site_header = 'Fantasy League Nepal Control Center'
    site_title = 'Fantasy League Nepal Admin'
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
	autocomplete_fields = ('team',)
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
	list_editable = ('gameweek_points', 'total_points')
	list_filter = ('rank',)
	search_fields = ('manager_name', 'team_name')
	ordering = ('rank',)
	list_per_page = 50
	fieldsets = (
		('League Ranking', {'fields': ('rank',)}),
		('Manager Details', {'fields': ('manager_name', 'team_name')}),
		('Points', {'fields': ('gameweek_points', 'total_points')}),
	)


class TeamAdmin(admin.ModelAdmin):
	list_display = ('name', 'short_name', 'strength', 'badge')
	search_fields = ('name', 'short_name')
	ordering = ('name',)


class FixtureAdmin(admin.ModelAdmin):
	list_display = ('gameweek', 'home_team', 'away_team', 'kickoff', 'difficulty')
	list_filter = ('gameweek', 'difficulty', 'home_team', 'away_team')
	ordering = ('gameweek', 'kickoff')


fantasy_admin_site.register(Player, PlayerAdmin)
fantasy_admin_site.register(LeagueEntry, LeagueEntryAdmin)
fantasy_admin_site.register(Team, TeamAdmin)
fantasy_admin_site.register(Fixture, FixtureAdmin)
