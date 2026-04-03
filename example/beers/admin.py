from django.contrib import admin

from .models import Beer, Brewery


@admin.register(Brewery)
class BreweryAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "state", "country"]
    search_fields = ["name", "city"]
    list_filter = ["country"]


@admin.register(Beer)
class BeerAdmin(admin.ModelAdmin):
    list_display = ["name", "style", "abv", "ibu", "brewery", "avg_rating"]
    search_fields = ["name", "style"]
    list_filter = ["style"]
    list_select_related = ["brewery"]
