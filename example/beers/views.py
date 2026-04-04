import hashlib
import hmac
import json
import os
import time

import jwt
import requests
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.models import AccessToken, Application, RefreshToken
from oauth2_provider.settings import oauth2_settings
from oauthlib.common import generate_token
from rest_framework import permissions, serializers as drf_serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Beer, Brewery, Rating
from .serializers import BeerSerializer, BrewerySerializer, RatingSerializer, RegisterSerializer


# --- Permissions ---

class IsAdminGroupMember(permissions.BasePermission):
    """Allow write access only to users in the 'admin' group."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.groups.filter(name="admin").exists())
        )


# --- DRF API ---

class BreweryViewSet(viewsets.ModelViewSet):
    queryset = Brewery.objects.all()
    serializer_class = BrewerySerializer
    permission_classes = [IsAdminGroupMember]


class BeerViewSet(viewsets.ModelViewSet):
    queryset = Beer.objects.select_related("brewery").all()
    serializer_class = BeerSerializer
    permission_classes = [IsAdminGroupMember]

    def get_queryset(self):
        qs = super().get_queryset()
        style = self.request.query_params.get("style")
        if style:
            qs = qs.filter(style=style)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        ordering = self.request.query_params.get("ordering", "name")
        if ordering in ("name", "-name", "abv", "-abv", "avg_rating", "-avg_rating"):
            qs = qs.order_by(ordering)
        return qs


class RatingViewSet(viewsets.ModelViewSet):
    queryset = Rating.objects.all()
    serializer_class = RatingSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        beer_id = self.request.query_params.get("beer_id")
        if beer_id:
            qs = qs.filter(beer_id=beer_id)
        return qs

    def perform_create(self, serializer):
        rating = serializer.save(user=self.request.user)
        # Recompute avg_rating on the beer
        stats = Rating.objects.filter(beer=rating.beer).aggregate(
            avg=Avg("score"), count=Count("id")
        )
        beer = rating.beer
        beer.avg_rating = round(stats["avg"] or 0, 1)
        beer.rating_count = stats["count"] or 0
        beer.save(update_fields=["avg_rating", "rating_count"])


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"id": user.pk, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        user = request.user
        if user.is_superuser or user.groups.filter(name="admin").exists():
            return Response(
                {"error": "Admin accounts cannot be deleted from the app."},
                status=status.HTTP_403_FORBIDDEN,
            )
        username = user.username
        # Delete user's ratings and recompute affected beers
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute(
            'DELETE FROM `beer-sample`.`_default`.`beers_rating` '
            'WHERE username = %s AND doc_type = "rating"',
            [username],
        )
        # Revoke all OAuth tokens
        AccessToken.objects.filter(user=user).delete()
        RefreshToken.objects.filter(user=user).delete()
        # Delete the user
        user.delete()
        return Response({"detail": "Account deleted"}, status=status.HTTP_200_OK)


# --- Template views ---

_cache = {"styles": None, "counts": {}, "ts": 0}

def _refresh_style_cache():
    """Cache top styles and counts using ORM aggregation."""
    from django.db.models import Count
    style_counts = (
        Beer.objects.exclude(style="")
        .values("style")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
    )
    counts = {"": sum(sc["cnt"] for sc in style_counts)}
    for sc in style_counts:
        counts[sc["style"]] = sc["cnt"]
    _cache["styles"] = [sc["style"] for sc in style_counts[:10]]
    _cache["counts"] = counts
    _cache["ts"] = time.time()


def beer_list_view(request):
    from django.core.paginator import Paginator

    # Cache styles and counts for 5 minutes
    if _cache["styles"] is None or time.time() - _cache["ts"] > 300:
        _refresh_style_cache()

    style = request.GET.get("style", "")
    search = request.GET.get("q", "")

    # Pure ORM queries
    qs = Beer.objects.order_by("name")
    if style:
        qs = qs.filter(style=style)
    if search:
        qs = qs.filter(name__icontains=search)

    # Use cached count to avoid COUNT(*) on every page load
    if not search:
        total_count = _cache["counts"].get(style, _cache["counts"].get("", 0))
    else:
        total_count = qs.count()

    per_page = 48
    page_num = max(1, int(request.GET.get("page", 1)))
    num_pages = max(1, (total_count + per_page - 1) // per_page)
    page_num = min(page_num, num_pages)
    offset = (page_num - 1) * per_page

    # Sliced queryset — avoids Paginator's extra COUNT query
    beers = list(qs[offset:offset + per_page])

    # Batch-fetch brewery names for this page only
    brewery_ids = {b.brewery_id for b in beers if b.brewery_id}
    brewery_names = {}
    if brewery_ids:
        brewery_names = dict(
            Brewery.objects.filter(pk__in=brewery_ids).values_list("pk", "name")
        )
    for b in beers:
        b.brewery_display = brewery_names.get(b.brewery_id, "")

    return render(request, "beers/beer_list.html", {
        "beers": beers,
        "styles": _cache["styles"],
        "active_style": style,
        "search_query": search,
        "page_num": page_num,
        "num_pages": num_pages,
        "has_previous": page_num > 1,
        "has_next": page_num < num_pages,
        "previous_page": page_num - 1,
        "next_page": page_num + 1,
        "total_count": total_count,
        "page_range": range(1, num_pages + 1),
    })


def beer_detail_view(request, pk):
    beer = Beer.objects.select_related("brewery").get(pk=pk)
    # Query ratings directly — mobile-created ratings may lack ORM FK fields
    from django.db import connection
    cursor = connection.cursor()
    cursor.execute(
        'SELECT username, score, created_at FROM `beer-sample`.`_default`.`beers_rating` '
        'WHERE beer_id = %s AND doc_type = "rating" ORDER BY created_at DESC',
        [pk],
    )
    ratings = [
        {"username": row[0], "score": row[1], "created_at": row[2]}
        for row in cursor.fetchall()
    ]
    return render(request, "beers/beer_detail.html", {"beer": beer, "ratings": ratings})


# --- Social Login Token Exchange ---

def _get_or_create_social_user(provider, social_id, email, full_name):
    """Find or create a Django user from a social login."""
    # Try to find existing user by email first
    user = None
    if email:
        user = User.objects.filter(email=email).first()
    if not user:
        # Create username from social ID
        username = f"{provider}_{social_id[:20]}"
        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
        else:
            user = User.objects.create_user(
                username=username,
                email=email or "",
                password=None,  # No password — social-only account
            )
            if full_name:
                parts = full_name.split(" ", 1)
                user.first_name = parts[0]
                if len(parts) > 1:
                    user.last_name = parts[1]
                user.save(update_fields=["first_name", "last_name"])
    return user


def _issue_oidc_tokens(user):
    """Issue OAuth2/OIDC tokens for the given user, matching DOT's format exactly."""
    import base64
    import datetime
    import uuid

    from cryptography.hazmat.primitives import serialization
    from django.conf import settings as django_settings
    from jwt.algorithms import RSAAlgorithm

    app = Application.objects.filter(client_id="brewsync-ios").first()
    if not app:
        raise ValueError("OAuth application 'brewsync-ios' not found")

    now = int(time.time())
    expires = now + oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS

    access = AccessToken.objects.create(
        user=user,
        application=app,
        token=generate_token(),
        expires=datetime.datetime.fromtimestamp(expires),
        scope="openid profile email",
    )
    refresh = RefreshToken.objects.create(
        user=user,
        application=app,
        token=generate_token(),
        access_token=access,
    )

    # Compute kid (RFC 7638 JWK Thumbprint) — matches what DOT publishes in JWKS
    private_key = oauth2_settings.OIDC_RSA_PRIVATE_KEY
    private_key_obj = serialization.load_pem_private_key(private_key.encode(), password=None)
    public_key_obj = private_key_obj.public_key()
    jwk_dict = json.loads(RSAAlgorithm.to_jwk(public_key_obj))
    thumbprint_input = json.dumps(
        {"e": jwk_dict["e"], "kty": jwk_dict["kty"], "n": jwk_dict["n"]},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    kid = base64.urlsafe_b64encode(hashlib.sha256(thumbprint_input).digest()).rstrip(b"=").decode()

    # Compute at_hash: left-half of SHA-256 of the access token, base64url-encoded
    at_digest = hashlib.sha256(access.token.encode()).digest()
    at_hash = base64.urlsafe_b64encode(at_digest[:16]).decode().rstrip("=")

    # Issuer must match what DOT serves at /.well-known/openid-configuration
    # DOT derives it from the request URL, but we don't have a request here.
    # Use DJANGO_CSRF_TRUSTED_ORIGINS or DJANGO_ALLOWED_HOSTS for the real domain.
    base_url = os.environ.get(
        "DJANGO_CSRF_TRUSTED_ORIGINS", ""
    ).split(",")[0].strip()
    if not base_url:
        host = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")[0].strip()
        base_url = f"https://{host}"
    issuer = base_url.rstrip("/") + "/o"

    # Build claims matching DOT's exact format
    groups = list(user.groups.values_list("name", flat=True))
    claims = {
        "aud": app.client_id,            # plain string, not array
        "iat": now,
        "at_hash": at_hash,
        "sub": str(user.pk),             # DOT uses user PK as string, not username
        "iss": issuer,
        "exp": expires,
        "auth_time": now,
        "jti": str(uuid.uuid4()),
        # Custom claims (from get_additional_claims)
        "preferred_username": user.username,
        "email": user.email,
        "groups": groups,
    }
    id_token_jwt = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})

    return {
        "access_token": access.token,
        "id_token": id_token_jwt,
        "refresh_token": refresh.token,
        "token_type": "Bearer",
        "expires_in": oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        "scope": "openid profile email",
    }


@method_decorator(csrf_exempt, name="dispatch")
class SocialTokenExchangeView(APIView):
    """Exchange a native Apple/Google social token for Django OIDC tokens.

    POST /api/auth/social/
    {
        "provider": "apple" | "google",
        "id_token": "<JWT from Apple/Google>",
        "authorization_code": "<optional, Apple first-time>",
        "full_name": "<optional, Apple first-time>"
    }
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # No auth needed — the social token IS the auth

    def post(self, request):
        provider = request.data.get("provider")
        id_token = request.data.get("id_token")

        if not provider or not id_token:
            return Response(
                {"error": "provider and id_token are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if provider == "apple":
                social_id, email = self._verify_apple(id_token)
                full_name = request.data.get("full_name", "")
            elif provider == "google":
                social_id, email = self._verify_google(id_token)
                full_name = request.data.get("full_name", "")
            else:
                return Response(
                    {"error": "provider must be 'apple' or 'google'"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = _get_or_create_social_user(provider, social_id, email, full_name)
            tokens = _issue_oidc_tokens(user)
            return Response(tokens)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )

    def _verify_apple(self, id_token_str):
        """Verify Apple ID token using Apple's public keys."""
        # Fetch Apple's public keys
        apple_keys_url = "https://appleid.apple.com/auth/keys"
        resp = requests.get(apple_keys_url, timeout=10)
        resp.raise_for_status()
        apple_keys = resp.json()

        # Decode header to find the key ID
        header = jwt.get_unverified_header(id_token_str)
        kid = header.get("kid")

        # Find matching key
        key_data = None
        for key in apple_keys["keys"]:
            if key["kid"] == kid:
                key_data = key
                break
        if not key_data:
            raise ValueError("Apple public key not found")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        # Accept both App ID (native iOS) and Services ID (web) as valid audiences
        valid_audiences = [
            os.environ.get("APPLE_CLIENT_ID", "com.brewsync.auth"),
            os.environ.get("APPLE_APP_ID", "com.brewsync.app"),
        ]
        claims = jwt.decode(
            id_token_str,
            public_key,
            algorithms=["RS256"],
            audience=valid_audiences,
            issuer="https://appleid.apple.com",
        )

        return claims["sub"], claims.get("email", "")

    def _verify_google(self, id_token_str):
        """Verify Google ID token using Google's tokeninfo endpoint."""
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token_str},
            timeout=10,
        )
        if resp.status_code != 200:
            raise ValueError("Invalid Google ID token")

        claims = resp.json()
        expected_client_id = os.environ.get("GOOGLE_IOS_CLIENT_ID", "")
        if expected_client_id and claims.get("aud") != expected_client_id:
            raise ValueError("Google token audience mismatch")

        return claims["sub"], claims.get("email", "")
