"""Custom OIDC claims for django-oauth-toolkit.

Includes user group memberships in the ID token so Couchbase App Services
can map the 'admin' group to a Sync Gateway role.
"""
from oauth2_provider.views.oidc import UserInfoView


def get_claims(request):
    """Return custom claims for the OIDC ID token / userinfo endpoint."""
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
