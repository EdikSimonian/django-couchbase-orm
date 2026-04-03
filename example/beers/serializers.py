from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Beer, Brewery, Rating


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


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = ["id", "beer", "user", "username", "score", "created_at"]
        read_only_fields = ["user", "username", "created_at"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
