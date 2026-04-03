from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Beer, Brewery
from .serializers import BeerSerializer, BrewerySerializer


# --- DRF API ---

class BreweryViewSet(viewsets.ModelViewSet):
    queryset = Brewery.objects.all()
    serializer_class = BrewerySerializer


class BeerViewSet(viewsets.ModelViewSet):
    queryset = Beer.objects.select_related("brewery").all()
    serializer_class = BeerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        style = self.request.query_params.get("style")
        if style:
            qs = qs.filter(style=style)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        ordering = self.request.query_params.get("ordering", "name")
        if ordering in ("name", "-name", "abv", "-abv", "avg_rating", "-avg_rating"):
            qs = qs.order_by(ordering)
        return qs


# --- Template views ---

def beer_list_view(request):
    beers = Beer.objects.select_related("brewery").all()
    breweries = Brewery.objects.all()
    styles = sorted(set(b.style for b in beers if b.style))
    return render(request, "beers/beer_list.html", {
        "beers": beers,
        "breweries": breweries,
        "styles": styles,
    })


def beer_detail_view(request, pk):
    beer = Beer.objects.select_related("brewery").get(pk=pk)
    return render(request, "beers/beer_detail.html", {"beer": beer})
