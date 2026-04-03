from django.db.models import Avg, Count
from django.shortcuts import render
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Beer, Brewery, Rating
from .serializers import BeerSerializer, BrewerySerializer, RatingSerializer, RegisterSerializer


# --- Permissions ---

class IsAdminGroupMember(permissions.BasePermission):
    """Allow write access only to users in the 'admin' group."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.groups.filter(name="admin").exists())
        )


# --- DRF API ---

class BreweryViewSet(viewsets.ModelViewSet):
    queryset = Brewery.objects.all()
    serializer_class = BrewerySerializer
    permission_classes = [IsAdminGroupMember]


class BeerViewSet(viewsets.ModelViewSet):
    queryset = Beer.objects.select_related("brewery").all()
    serializer_class = BeerSerializer
    permission_classes = [IsAdminGroupMember]

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


class RatingViewSet(viewsets.ModelViewSet):
    queryset = Rating.objects.all()
    serializer_class = RatingSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        beer_id = self.request.query_params.get("beer_id")
        if beer_id:
            qs = qs.filter(beer_id=beer_id)
        return qs

    def perform_create(self, serializer):
        rating = serializer.save(user=self.request.user)
        # Recompute avg_rating on the beer
        stats = Rating.objects.filter(beer=rating.beer).aggregate(
            avg=Avg("score"), count=Count("id")
        )
        beer = rating.beer
        beer.avg_rating = round(stats["avg"] or 0, 1)
        beer.rating_count = stats["count"] or 0
        beer.save(update_fields=["avg_rating", "rating_count"])


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"id": user.pk, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


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
