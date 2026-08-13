from django.db import models


class Team(models.Model):
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
