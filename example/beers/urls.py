from django.urls import path

from . import views

app_name = "beers"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("breweries/", views.brewery_list, name="brewery_list"),
    path("breweries/create/", views.brewery_create, name="brewery_create"),
    path("breweries/<path:brewery_id>/", views.brewery_detail, name="brewery_detail"),
    path("breweries/<path:brewery_id>/edit/", views.brewery_edit, name="brewery_edit"),
    path("breweries/<path:brewery_id>/delete/", views.brewery_delete, name="brewery_delete"),

    path("beers/", views.beer_list, name="beer_list"),
    path("beers/create/", views.beer_create, name="beer_create"),
    path("beers/<path:beer_id>/", views.beer_detail, name="beer_detail"),
    path("beers/<path:beer_id>/edit/", views.beer_edit, name="beer_edit"),
    path("beers/<path:beer_id>/delete/", views.beer_delete, name="beer_delete"),
]
