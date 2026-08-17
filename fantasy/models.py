from django.db import models


class Team(models.Model):
	fpl_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
	name = models.CharField(max_length=100)
	short_name = models.CharField(max_length=8)
	strength = models.PositiveSmallIntegerField(default=3)
	badge = models.CharField(max_length=4, default='⚽')

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name


class Player(models.Model):
	class Position(models.TextChoices):
		GOALKEEPER = 'GK', 'Goalkeeper'
		DEFENDER = 'DEF', 'Defender'
		MIDFIELDER = 'MID', 'Midfielder'
		FORWARD = 'FWD', 'Forward'

	fpl_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
	name = models.CharField(max_length=120)
	team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
	position = models.CharField(max_length=3, choices=Position.choices)
	price = models.DecimalField(max_digits=4, decimal_places=1)
	total_points = models.PositiveIntegerField(default=0)
	selected_by_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	goals = models.PositiveSmallIntegerField(default=0)
	assists = models.PositiveSmallIntegerField(default=0)
	clean_sheets = models.PositiveSmallIntegerField(default=0)
	photo_url = models.URLField(blank=True)

	class Meta:
		ordering = ['-total_points', 'name']

	def __str__(self):
		return f'{self.name} ({self.team.short_name})'


class Fixture(models.Model):
	fpl_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
	home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_fixtures')
	away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_fixtures')
	kickoff = models.DateTimeField()
	gameweek = models.PositiveSmallIntegerField(default=1)
	difficulty = models.PositiveSmallIntegerField(default=3)

	class Meta:
		ordering = ['kickoff']

	def __str__(self):
		return f'GW{self.gameweek}: {self.home_team.short_name} vs {self.away_team.short_name}'


class LeagueEntry(models.Model):
	manager_name = models.CharField(max_length=100)
	team_name = models.CharField(max_length=100)
	total_points = models.PositiveIntegerField(default=0)
	gameweek_points = models.PositiveIntegerField(default=0)
	rank = models.PositiveIntegerField(unique=True)

	class Meta:
		ordering = ['rank']
		verbose_name_plural = 'League entries'

	def __str__(self):
		return f'#{self.rank} {self.manager_name}'


class SiteSettings(models.Model):
	"""Singleton row holding site-wide branding. Always saved/loaded at
	pk=1 so there's exactly one place to manage the logo shown across the
	public site and the admin panel."""
	logo = models.ImageField(
		upload_to='branding/',
		blank=True,
		null=True,
		help_text='Shown in the sidebar/brand mark across the site and admin. Square-ish images work best.',
	)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'Site Branding'
		verbose_name_plural = 'Site Branding'

	def __str__(self):
		return 'Site Branding'

	def save(self, *args, **kwargs):
		self.pk = 1
		super().save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		pass

	@classmethod
	def load(cls):
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj


class CaptainGameweekScore(models.Model):
	"""One row per (manager, gameweek): their total gameweek points, plus
	who they captained and how many points that captain contributed. Only
	ever written for FINISHED gameweeks, since those points never change
	again - the season-total captain leaderboard and the monthly-points
	leaderboard both sum straight from this table instead of re-fetching
	every manager's picks for every past gameweek on every page load. The
	current, still-in-progress gameweek is always fetched live and added on
	top at render time instead of being stored here."""
	entry_id = models.PositiveIntegerField()
	manager_name = models.CharField(max_length=100)
	team_name = models.CharField(max_length=100)
	gameweek = models.PositiveSmallIntegerField()
	gameweek_points = models.IntegerField(default=0)
	event_transfers_cost = models.PositiveSmallIntegerField(
		default=0,
		help_text='Points deducted for transfer hits taken this gameweek (e.g. 2 extra transfers = 4).',
	)
	captain_name = models.CharField(max_length=120, blank=True)
	captain_points = models.IntegerField(default=0)

	class Meta:
		unique_together = ('entry_id', 'gameweek')
		ordering = ['gameweek']
		verbose_name = 'Captain gameweek score'
		verbose_name_plural = 'Captain gameweek scores'

	def __str__(self):
		return f'GW{self.gameweek}: {self.manager_name} ({self.captain_points} captain pts)'
