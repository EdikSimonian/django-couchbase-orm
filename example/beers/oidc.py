"""Custom OIDC claims for django-oauth-toolkit.

Includes user group memberships and preferred_username in both the
ID token and the userinfo endpoint so Couchbase App Services can
map users and roles correctly.
"""
from oauth2_provider.oauth2_validators import OAuth2Validator


class CustomOIDCValidator(OAuth2Validator):
    """Add preferred_username and groups to the ID token JWT."""

    oidc_claim_scope = None  # Include all claims regardless of scope

    def get_additional_claims(self, request):
        user = request.user
        return {
            "preferred_username": user.username,
            "email": user.email,
            "groups": list(user.groups.values_list("name", flat=True)),
        }

    def get_userinfo_claims(self, request):
        user = request.user
        claims = {
            "sub": user.username,
            "preferred_username": user.username,
            "email": user.email,
            "groups": list(user.groups.values_list("name", flat=True)),
        }
        if user.first_name:
            claims["given_name"] = user.first_name
        if user.last_name:
            claims["family_name"] = user.last_name
        return claims
