from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models


def _shrink_image(image_field, max_dimension):
	"""Downscale an uploaded image in place if its longest side exceeds
	max_dimension, so a multi-megapixel phone photo doesn't ship in full
	for something that renders as a small icon/banner. No-op if the file
	is already small enough (including on every subsequent save of an
	already-processed image, so this is safe to call unconditionally)."""
	if not image_field or not image_field.name:
		return
	try:
		from PIL import Image
	except ImportError:
		return
	try:
		image_field.open()
		img = Image.open(image_field)
		img.load()
	except Exception:
		return

	width, height = img.size
	if max(width, height) <= max_dimension:
		return

	ratio = max_dimension / max(width, height)
	new_size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
	has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
	img = img.convert('RGBA') if has_alpha else img.convert('RGB')
	resized = img.resize(new_size, Image.LANCZOS)

	buffer = BytesIO()
	if has_alpha:
		# Truecolor RGBA compresses poorly for flat-color logos/graphics that
		# were originally palette-based - try quantizing to an adaptive
		# palette too and keep whichever actually comes out smaller.
		resized.save(buffer, format='PNG', optimize=True)
		quantized_buffer = BytesIO()
		try:
			resized.quantize(colors=256, method=Image.FASTOCTREE).save(quantized_buffer, format='PNG', optimize=True)
			if quantized_buffer.tell() < buffer.tell():
				buffer = quantized_buffer
		except Exception:
			pass
	else:
		resized.save(buffer, format='JPEG', quality=85, optimize=True)
	buffer.seek(0)
	image_field.save(image_field.name, ContentFile(buffer.read()), save=False)


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
		# Renders as a small ~40px mark everywhere it's used - cap well above
		# that for retina screens without shipping a multi-megapixel photo.
		_shrink_image(self.logo, max_dimension=200)
		super().save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		pass

	@classmethod
	def load(cls):
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj


class PageAdvertisement(models.Model):
	"""One row per public page, holding the ad banner shown in that page's
	league-name card. Rows are seeded for every Page choice by migration
	0008 and are never added/removed from the admin - only their image and
	link are ever edited - so each page always has exactly one ad slot to
	manage, independently of the others."""
	class Page(models.TextChoices):
		CAPTAIN_MODE = 'captain_mode', 'Captain Mode'
		CLASSIC_LEAGUE = 'classic_league', 'Classic League'
		GAMEWEEK_WINNERS = 'gameweek_winners', 'Gameweek Winners'
		MANAGER_OF_THE_MONTH = 'manager_of_the_month', 'Manager of the Month'

	page = models.CharField(max_length=32, choices=Page.choices, unique=True)
	image = models.ImageField(
		upload_to='advertisements/',
		blank=True,
		null=True,
		help_text='Shown in the advertisement half of this page\'s banner. Leave blank to show no ad. Landscape images work best.',
	)
	link_url = models.URLField(blank=True, help_text='Optional - clicking the ad image opens this link in a new tab.')
	alt_text = models.CharField(max_length=150, blank=True, help_text='Accessibility text for the ad image.')
	caption = models.CharField(
		max_length=200,
		blank=True,
		help_text='Optional short text shown to the right of the ad image (e.g. a tagline or short description).',
	)
	instagram_url = models.URLField(blank=True, help_text='Optional - shows a small Instagram icon linking here.')
	facebook_url = models.URLField(blank=True, help_text='Optional - shows a small Facebook icon linking here.')
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['page']
		verbose_name = 'Page Advertisement'
		verbose_name_plural = 'Page Advertisements'

	def __str__(self):
		return self.get_page_display()

	def save(self, *args, **kwargs):
		# Renders capped at 64px tall in the banner - cap the source well
		# above that for retina/wide layouts without shipping full-res photos.
		_shrink_image(self.image, max_dimension=800)
		super().save(*args, **kwargs)


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
