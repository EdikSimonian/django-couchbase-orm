"""Embed titles from wagtailcore_page into home_blogpage documents."""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Embed title and slug into all blogpage documents for mobile sync"

    def handle(self, *args, **options):
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE `beer-sample`.`_default`.`home_blogpage` b '
            'SET b.title = (SELECT RAW p.title FROM `beer-sample`.`_default`.`wagtailcore_page` p '
            'WHERE META(p).id = TO_STRING(b.page_ptr_id))[0], '
            'b.slug = (SELECT RAW p.slug FROM `beer-sample`.`_default`.`wagtailcore_page` p '
            'WHERE META(p).id = TO_STRING(b.page_ptr_id))[0] '
            'WHERE b.page_ptr_id IS VALUED'
        )
        self.stdout.write(self.style.SUCCESS(f"Updated {cursor.rowcount} blogpage docs"))
