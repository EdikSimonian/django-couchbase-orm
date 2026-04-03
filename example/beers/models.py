from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Brewery(models.Model):
    doc_type = models.CharField(max_length=50, default="brewery", editable=False)
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "breweries"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, **kwargs):
        self.doc_type = "brewery"
        super().save(**kwargs)


class Beer(models.Model):
    STYLE_CHOICES = [
        ("IPA", "IPA"),
        ("Pale Ale", "Pale Ale"),
        ("Stout", "Stout"),
        ("Porter", "Porter"),
        ("Lager", "Lager"),
        ("Pilsner", "Pilsner"),
        ("Wheat", "Wheat"),
        ("Sour", "Sour"),
        ("Amber", "Amber"),
        ("Brown Ale", "Brown Ale"),
        ("Belgian", "Belgian"),
        ("Saison", "Saison"),
        ("Hazy IPA", "Hazy IPA"),
        ("Double IPA", "Double IPA"),
        ("Other", "Other"),
    ]

    doc_type = models.CharField(max_length=50, default="beer", editable=False)
    name = models.CharField(max_length=200)
    abv = models.FloatField(verbose_name="ABV %", null=True, blank=True)
    ibu = models.IntegerField(verbose_name="IBU", null=True, blank=True)
    style = models.CharField(max_length=100, blank=True, default="")
    brewery = models.ForeignKey(
        Brewery, on_delete=models.CASCADE, null=True, blank=True, related_name="beers"
    )
    description = models.TextField(blank=True, default="")
    image_url = models.URLField(blank=True, default="")
    avg_rating = models.FloatField(default=0.0)
    rating_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.style})" if self.style else self.name

    def save(self, **kwargs):
        self.doc_type = "beer"
        super().save(**kwargs)


class Rating(models.Model):
    doc_type = models.CharField(max_length=50, default="rating", editable=False)
    beer = models.ForeignKey(Beer, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beer_ratings"
    )
    username = models.CharField(max_length=150)
    score = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("beer", "user")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username}: {self.beer.name} = {self.score}"

    def save(self, **kwargs):
        self.doc_type = "rating"
        self.username = self.user.username if self.user_id else self.username
        super().save(**kwargs)
