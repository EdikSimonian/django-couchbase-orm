"""Seed the database with craft brewery and beer data."""

from django.core.management.base import BaseCommand

from beers.models import Beer, Brewery

BREWERIES = [
    {"name": "Sierra Nevada", "city": "Chico", "state": "CA", "country": "USA",
     "description": "Pioneering craft brewery founded in 1980."},
    {"name": "Dogfish Head", "city": "Milton", "state": "DE", "country": "USA",
     "description": "Off-centered ales for off-centered people."},
    {"name": "Stone Brewing", "city": "Escondido", "state": "CA", "country": "USA",
     "description": "Arrogant ales brewed with passion."},
    {"name": "Founders Brewing", "city": "Grand Rapids", "state": "MI", "country": "USA",
     "description": "Brewed for us. Period."},
    {"name": "Bell's Brewery", "city": "Comstock", "state": "MI", "country": "USA",
     "description": "Inspired brewing since 1985."},
    {"name": "Lagunitas", "city": "Petaluma", "state": "CA", "country": "USA",
     "description": "Beer speaks, people mumble."},
    {"name": "Brooklyn Brewery", "city": "Brooklyn", "state": "NY", "country": "USA",
     "description": "Crafted in Brooklyn since 1988."},
]

BEERS = [
    {"name": "Pale Ale", "abv": 5.6, "ibu": 38, "style": "Pale Ale", "brewery": "Sierra Nevada",
     "description": "The one that started it all. Cascade hops with caramel malt backbone."},
    {"name": "Torpedo Extra IPA", "abv": 7.2, "ibu": 65, "style": "IPA", "brewery": "Sierra Nevada",
     "description": "Aggressive yet balanced with tropical hop character."},
    {"name": "Hazy Little Thing", "abv": 6.7, "ibu": 35, "style": "Hazy IPA", "brewery": "Sierra Nevada",
     "description": "Unfiltered, unprocessed, straight from the tank."},
    {"name": "60 Minute IPA", "abv": 6.0, "ibu": 60, "style": "IPA", "brewery": "Dogfish Head",
     "description": "Continuously hopped for 60 minutes. Citrus and pine."},
    {"name": "90 Minute IPA", "abv": 9.0, "ibu": 90, "style": "Double IPA", "brewery": "Dogfish Head",
     "description": "Imperial IPA with a boatload of hops."},
    {"name": "SeaQuench Ale", "abv": 4.9, "ibu": 10, "style": "Sour", "brewery": "Dogfish Head",
     "description": "Session sour with lime peel, sea salt, and black limes."},
    {"name": "Stone IPA", "abv": 6.9, "ibu": 71, "style": "IPA", "brewery": "Stone Brewing",
     "description": "The quintessential West Coast IPA. Citrus and pine."},
    {"name": "Arrogant Bastard Ale", "abv": 7.2, "ibu": 100, "style": "Amber", "brewery": "Stone Brewing",
     "description": "You probably won't like it. It's quite aggressive."},
    {"name": "Ruination IPA", "abv": 8.5, "ibu": 100, "style": "Double IPA", "brewery": "Stone Brewing",
     "description": "A liquid poem to hops. Devastatingly hoppy."},
    {"name": "All Day IPA", "abv": 4.7, "ibu": 42, "style": "IPA", "brewery": "Founders Brewing",
     "description": "Session IPA you can drink all day. Balanced and refreshing."},
    {"name": "Breakfast Stout", "abv": 8.3, "ibu": 60, "style": "Stout", "brewery": "Founders Brewing",
     "description": "Brewed with coffee, chocolate, and oats. Rich and decadent."},
    {"name": "Dirty Bastard", "abv": 8.5, "ibu": 50, "style": "Brown Ale", "brewery": "Founders Brewing",
     "description": "Scotch ale with complex malt character and warming finish."},
    {"name": "Two Hearted Ale", "abv": 7.0, "ibu": 55, "style": "IPA", "brewery": "Bell's Brewery",
     "description": "Defined by Centennial hops. America's best beer."},
    {"name": "Oberon", "abv": 5.8, "ibu": 22, "style": "Wheat", "brewery": "Bell's Brewery",
     "description": "A summer wheat ale spiced with coriander. An icon."},
    {"name": "Hopslam", "abv": 10.0, "ibu": 70, "style": "Double IPA", "brewery": "Bell's Brewery",
     "description": "Double IPA with honey. Released once a year."},
    {"name": "IPA", "abv": 6.2, "ibu": 52, "style": "IPA", "brewery": "Lagunitas",
     "description": "Generously hoppy with a malty backbone."},
    {"name": "Little Sumpin' Sumpin'", "abv": 7.5, "ibu": 65, "style": "Wheat", "brewery": "Lagunitas",
     "description": "Really hoppy wheat ale. Smooth and complex."},
    {"name": "A Little Sumpin' Extra", "abv": 8.5, "ibu": 80, "style": "Belgian", "brewery": "Lagunitas",
     "description": "Belgian-inspired strong ale with hop punch."},
    {"name": "Brooklyn Lager", "abv": 5.2, "ibu": 33, "style": "Lager", "brewery": "Brooklyn Brewery",
     "description": "The flagship amber lager. Smooth with a hoppy finish."},
    {"name": "Brooklyn Defender IPA", "abv": 5.5, "ibu": 55, "style": "IPA", "brewery": "Brooklyn Brewery",
     "description": "Crisp, citrusy IPA with dry-hop character."},
]


class Command(BaseCommand):
    help = "Seed the database with craft beer and brewery data"

    def handle(self, *args, **options):
        # Create breweries
        brewery_map = {}
        for data in BREWERIES:
            brewery, created = Brewery.objects.get_or_create(
                name=data["name"],
                defaults={k: v for k, v in data.items() if k != "name"},
            )
            brewery_map[data["name"]] = brewery
            status = "Created" if created else "Exists"
            self.stdout.write(f"  {status}: {brewery.name}")

        # Create beers
        for data in BEERS:
            brewery = brewery_map.get(data.pop("brewery"))
            beer, created = Beer.objects.get_or_create(
                name=data["name"],
                brewery=brewery,
                defaults=data,
            )
            status = "Created" if created else "Exists"
            self.stdout.write(f"  {status}: {beer.name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: {Brewery.objects.count()} breweries, {Beer.objects.count()} beers"
            )
        )
