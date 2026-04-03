from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("beers", views.BeerViewSet)
router.register("breweries", views.BreweryViewSet)
router.register("ratings", views.RatingViewSet)

urlpatterns = [
    # API
    path("api/", include(router.urls)),
    path("api/auth/register/", views.RegisterView.as_view(), name="api-register"),
    # Web UI
    path("beers/", views.beer_list_view, name="beer-list"),
    path("beers/<int:pk>/", views.beer_detail_view, name="beer-detail"),
]
