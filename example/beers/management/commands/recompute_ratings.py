"""Recompute avg_rating and rating_count on all beers from Rating documents."""
from django.core.management.base import BaseCommand
from django.db.models import Avg, Count

from beers.models import Beer, Rating


class Command(BaseCommand):
    help = "Recompute avg_rating and rating_count on all beers from ratings"

    def handle(self, *args, **options):
        stats = (
            Rating.objects.values("beer_id")
            .annotate(avg=Avg("score"), count=Count("id"))
        )
        updated = 0
        for entry in stats:
            Beer.objects.filter(pk=entry["beer_id"]).update(
                avg_rating=round(entry["avg"] or 0, 1),
                rating_count=entry["count"] or 0,
            )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Recomputed ratings for {updated} beers."))
