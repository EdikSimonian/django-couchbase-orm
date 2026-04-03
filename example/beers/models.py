from django.db import models


class Brewery(models.Model):
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
