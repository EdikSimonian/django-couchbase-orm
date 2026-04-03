"""Set doc_type on existing Beer and Brewery documents that don't have it."""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Set doc_type field on existing Beer and Brewery documents"

    def handle(self, *args, **options):
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE `beer-sample`.`_default`.`beers_beer` "
            "SET doc_type = 'beer' WHERE doc_type IS NOT VALUED"
        )
        self.stdout.write(f"Updated beers: {cursor.rowcount}")

        cursor.execute(
            "UPDATE `beer-sample`.`_default`.`beers_brewery` "
            "SET doc_type = 'brewery' WHERE doc_type IS NOT VALUED"
        )
        self.stdout.write(f"Updated breweries: {cursor.rowcount}")

        self.stdout.write(self.style.SUCCESS("Done!"))
