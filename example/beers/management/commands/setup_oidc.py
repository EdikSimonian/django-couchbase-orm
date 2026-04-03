"""Create the OIDC application for the iOS app."""
from django.core.management.base import BaseCommand
from oauth2_provider.models import Application
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Create the BrewSync OIDC application for iOS"

    def handle(self, *args, **options):
        client_id = "brewsync-ios"
        app, created = Application.objects.get_or_create(
            client_id=client_id,
            defaults={
                "name": "BrewSync iOS",
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "redirect_uris": "brewsync://callback",
                "algorithm": Application.RS256_ALGORITHM,
                "skip_authorization": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Created OIDC application: client_id={client_id}"
            ))
        else:
            self.stdout.write(f"OIDC application already exists: client_id={client_id}")

        # Ensure admin group exists
        from django.contrib.auth.models import Group
        group, created = Group.objects.get_or_create(name="admin")
        if created:
            self.stdout.write(self.style.SUCCESS("Created 'admin' group"))
        else:
            self.stdout.write("'admin' group already exists")

        # Add superusers to admin group
        for user in User.objects.filter(is_superuser=True):
            if not user.groups.filter(name="admin").exists():
                user.groups.add(group)
                self.stdout.write(f"  Added {user.username} to admin group")
