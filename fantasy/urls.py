from django.urls import path

from .views import (
    captain_mode,
    classic_league,
    gameweek_winners,
    home,
    league_live_data,
    live_gameweek,
    manager_of_the_month,
)

app_name = 'fantasy'

urlpatterns = [
    path('', home, name='home'),
    path('live-gameweek/', live_gameweek, name='live_gameweek'),
    path('captain-mode/', captain_mode, name='captain_mode'),
    path('gameweek-winners/', gameweek_winners, name='gameweek_winners'),
    path('manager-of-the-month/', manager_of_the_month, name='manager_of_the_month'),
    path('classic-league/', classic_league, name='classic_league'),
    path('api/league-live-data/', league_live_data, name='league_live_data'),
]
