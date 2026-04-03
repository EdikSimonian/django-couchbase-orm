from rest_framework import serializers

from .models import Beer, Brewery


class BrewerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Brewery
        fields = ["id", "name", "city", "state", "country", "description", "website"]


class BeerSerializer(serializers.ModelSerializer):
    brewery_name = serializers.CharField(source="brewery.name", read_only=True, default="")

    class Meta:
        model = Beer
        fields = [
            "id", "name", "abv", "ibu", "style", "brewery", "brewery_name",
            "description", "image_url", "avg_rating", "rating_count",
            "created_at", "updated_at",
        ]
