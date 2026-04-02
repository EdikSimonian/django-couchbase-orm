import math
import re
import time

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from django_couchbase_orm.queryset.q import Q

from .documents import Beer, Brewery

# Simple in-memory cache for expensive queries that rarely change
_cache = {}
CACHE_TTL = 300  # 5 minutes


def _get_cached(key, ttl=CACHE_TTL):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def _set_cached(key, value):
    _cache[key] = (time.time(), value)


# ============================================================
# Validation helpers
# ============================================================

# Only allow alphanumeric, underscores, hyphens for document IDs
_VALID_DOC_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,127}$")

# Reserved prefixes that user-created documents must not use
_RESERVED_PREFIXES = ("session:", "user::", "_type", "_system")


def _validate_doc_id(raw_id: str, doc_prefix: str) -> str:
    """Validate and namespace a user-supplied document ID."""
    cleaned = raw_id.strip().replace(" ", "_").lower()
    if not cleaned:
        raise ValueError("Document ID is required.")
    prefixed = f"{doc_prefix}{cleaned}"
    if not _VALID_DOC_ID.match(cleaned):
        raise ValueError("ID must be alphanumeric with underscores/hyphens, max 128 chars.")
    for prefix in _RESERVED_PREFIXES:
        if prefixed.startswith(prefix):
            raise ValueError(f"ID must not start with reserved prefix '{prefix}'.")
    return prefixed


def _safe_page(request) -> int:
    """Parse and validate page parameter."""
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    return min(page, 10000)


def _safe_float(value: str) -> float | None:
    """Parse a float from user input, rejecting NaN/Inf."""
    if not value or not value.strip():
        return None
    try:
        f = float(value)
    except (ValueError, TypeError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _validate_url(url: str | None) -> str | None:
    """Ensure URL uses http/https scheme."""
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return None
    return url


# ============================================================
# Auth views
# ============================================================


MAX_LOGIN_ATTEMPTS = 5
LOGIN_COOLDOWN_SECONDS = 300  # 5 minutes


def login_view(request):
    if request.user.is_authenticated:
        return redirect("beers:home")

    if request.method == "POST":
        from django_couchbase_orm.contrib.auth.backend import CouchbaseAuthBackend

        # Rate limiting via session
        attempts = request.session.get("_login_attempts", 0)
        lockout_until = request.session.get("_login_lockout", 0)
        if lockout_until and time.time() < lockout_until:
            remaining = int(lockout_until - time.time())
            messages.error(request, f"Too many failed attempts. Try again in {remaining} seconds.")
            return render(request, "beers/login.html")

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        backend = CouchbaseAuthBackend()
        user = backend.authenticate(request, username=username, password=password)
        if user is not None:
            # Cycle the session key to prevent session fixation
            request.session.cycle_key()
            request.session.pop("_login_attempts", None)
            request.session.pop("_login_lockout", None)
            request.session["_auth_user_id"] = user.pk
            request.session["_auth_user_backend"] = (
                "django_couchbase_orm.contrib.auth.backend.CouchbaseAuthBackend"
            )
            messages.success(request, f"Welcome back, {user.get_short_name()}!")
            return redirect("beers:home")
        else:
            attempts += 1
            request.session["_login_attempts"] = attempts
            if attempts >= MAX_LOGIN_ATTEMPTS:
                request.session["_login_lockout"] = time.time() + LOGIN_COOLDOWN_SECONDS
                messages.error(
                    request,
                    f"Too many failed attempts. Account locked for {LOGIN_COOLDOWN_SECONDS // 60} minutes.",
                )
            else:
                messages.error(request, "Invalid username or password.")

    return render(request, "beers/login.html")


def logout_view(request):
    request.session.flush()
    messages.info(request, "You have been logged out.")
    return redirect("beers:home")


def _get_current_user(request):
    """Get the Couchbase User from the session, or None."""
    user_id = request.session.get("_auth_user_id")
    if not user_id:
        return None
    from django_couchbase_orm.contrib.auth.models import User

    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


def _login_required(view_func):
    """Decorator that requires Couchbase auth login."""

    def wrapper(request, *args, **kwargs):
        user = _get_current_user(request)
        if user is None:
            messages.warning(request, "Please log in to access this page.")
            return redirect("beers:login")
        request.cb_user = user
        return view_func(request, *args, **kwargs)

    return wrapper


# ============================================================
# Read views
# ============================================================


async def home(request):
    import asyncio

    # Cache counts for 5 min — they rarely change
    cached_counts = _get_cached("home_counts")
    if cached_counts:
        brewery_count, beer_count = cached_counts
        featured = await Brewery.objects.order_by("name")[:12].alist()
    else:
        brewery_count, beer_count, featured = await asyncio.gather(
            Brewery.objects.acount(),
            Beer.objects.acount(),
            Brewery.objects.order_by("name")[:12].alist(),
        )
        _set_cached("home_counts", (brewery_count, beer_count))

    cb_user = _get_current_user(request)

    return render(request, "beers/home.html", {
        "brewery_count": brewery_count,
        "beer_count": beer_count,
        "featured_breweries": featured,
        "cb_user": cb_user,
    })


async def brewery_list(request):
    import asyncio

    search = request.GET.get("q", "").strip()[:200]
    page = _safe_page(request)
    per_page = 20

    qs = Brewery.objects.order_by("name")
    if search:
        qs = qs.filter(name__icontains=search)

    total, breweries = await asyncio.gather(
        qs.acount(),
        qs[(page - 1) * per_page : page * per_page].alist(),
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    return render(request, "beers/brewery_list.html", {
        "breweries": breweries,
        "search": search,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "cb_user": _get_current_user(request),
    })


def brewery_detail(request, brewery_id):
    try:
        brewery = Brewery.objects.get(pk=brewery_id)
    except Brewery.DoesNotExist:
        raise Http404("Brewery not found")

    beers = list(Beer.objects.filter(brewery_id=brewery_id).order_by("name"))

    return render(request, "beers/brewery_detail.html", {
        "brewery": brewery,
        "brewery_id": brewery_id,
        "beers": beers,
        "cb_user": _get_current_user(request),
    })


async def beer_list(request):
    import asyncio

    search = request.GET.get("q", "").strip()[:200]
    style = request.GET.get("style", "").strip()[:200]
    page = _safe_page(request)
    per_page = 20

    qs = Beer.objects.order_by("name")
    if search:
        qs = qs.filter(name__icontains=search)
    if style:
        qs = qs.filter(style=style)

    # Run count and page fetch concurrently
    total, beers = await asyncio.gather(
        qs.acount(),
        qs[(page - 1) * per_page : page * per_page].alist(),
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    # Cache styles dropdown — rarely changes
    styles = _get_cached("beer_styles")
    if styles is None:
        style_rows = await Beer.objects.values("style").order_by("style").alist()
        seen = set()
        styles = []
        for row in style_rows:
            s = row.get("style")
            if s and s not in seen:
                seen.add(s)
                styles.append(s)
        _set_cached("beer_styles", styles)

    return render(request, "beers/beer_list.html", {
        "beers": beers,
        "search": search,
        "selected_style": style,
        "styles": styles,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "cb_user": _get_current_user(request),
    })


def beer_detail(request, beer_id):
    try:
        beer = Beer.objects.get(pk=beer_id)
    except Beer.DoesNotExist:
        raise Http404("Beer not found")

    brewery = None
    if beer.brewery_id:
        try:
            brewery = Brewery.objects.get(pk=beer.brewery_id)
        except Brewery.DoesNotExist:
            pass

    return render(request, "beers/beer_detail.html", {
        "beer": beer,
        "beer_id": beer_id,
        "brewery": brewery,
        "cb_user": _get_current_user(request),
    })


# ============================================================
# CRUD views (login required)
# ============================================================


@_login_required
def brewery_create(request):
    if request.method == "POST":
        try:
            doc_id = _validate_doc_id(request.POST.get("id", ""), "brewery::")
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, "beers/brewery_form.html", {
                "action": "Create", "cb_user": request.cb_user,
            })

        brewery = Brewery(
            _id=doc_id,
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip() or None,
            city=request.POST.get("city", "").strip() or None,
            state=request.POST.get("state", "").strip() or None,
            country=request.POST.get("country", "").strip() or None,
            phone=request.POST.get("phone", "").strip() or None,
            website=_validate_url(request.POST.get("website", "").strip()),
            code=request.POST.get("code", "").strip() or None,
        )
        brewery.save()
        messages.success(request, f"Brewery '{brewery.name}' created.")
        return redirect("beers:brewery_detail", brewery_id=brewery.pk)

    return render(request, "beers/brewery_form.html", {
        "action": "Create",
        "cb_user": request.cb_user,
    })


@_login_required
def brewery_edit(request, brewery_id):
    try:
        brewery = Brewery.objects.get(pk=brewery_id)
    except Brewery.DoesNotExist:
        raise Http404("Brewery not found")

    if request.method == "POST":
        try:
            brewery._data["name"] = request.POST.get("name", "").strip()
            brewery._data["description"] = request.POST.get("description", "").strip() or None
            brewery._data["city"] = request.POST.get("city", "").strip() or None
            brewery._data["state"] = request.POST.get("state", "").strip() or None
            brewery._data["country"] = request.POST.get("country", "").strip() or None
            brewery._data["phone"] = request.POST.get("phone", "").strip() or None
            brewery._data["website"] = _validate_url(request.POST.get("website", "").strip())
            brewery._data["code"] = request.POST.get("code", "").strip() or None
            brewery.save()
            messages.success(request, f"Brewery '{brewery.name}' updated.")
            return redirect("beers:brewery_detail", brewery_id=brewery.pk)
        except Exception as e:
            messages.error(request, f"Failed to save: {e}")

    return render(request, "beers/brewery_form.html", {
        "action": "Edit",
        "brewery": brewery,
        "brewery_id": brewery_id,
        "cb_user": request.cb_user,
    })


@_login_required
def brewery_delete(request, brewery_id):
    try:
        brewery = Brewery.objects.get(pk=brewery_id)
    except Brewery.DoesNotExist:
        raise Http404("Brewery not found")

    if request.method == "POST":
        name = brewery.name
        brewery.delete()
        messages.success(request, f"Brewery '{name}' deleted.")
        return redirect("beers:brewery_list")

    return render(request, "beers/confirm_delete.html", {
        "object_type": "Brewery",
        "object_name": brewery.name,
        "cancel_url": "beers:brewery_detail",
        "cancel_id": brewery_id,
        "cb_user": request.cb_user,
    })


@_login_required
def beer_create(request):
    brewery_id = request.GET.get("brewery", "")

    if request.method == "POST":
        try:
            doc_id = _validate_doc_id(request.POST.get("id", ""), "beer::")
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, "beers/beer_form.html", {
                "action": "Create", "brewery_id": brewery_id, "cb_user": request.cb_user,
            })

        beer = Beer(
            _id=doc_id,
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip() or None,
            abv=_safe_float(request.POST.get("abv", "")),
            ibu=_safe_float(request.POST.get("ibu", "")),
            srm=_safe_float(request.POST.get("srm", "")),
            style=request.POST.get("style", "").strip() or None,
            category=request.POST.get("category", "").strip() or None,
            brewery_id=request.POST.get("brewery_id", "").strip() or None,
        )
        beer.save()
        messages.success(request, f"Beer '{beer.name}' created.")
        return redirect("beers:beer_detail", beer_id=beer.pk)

    return render(request, "beers/beer_form.html", {
        "action": "Create",
        "brewery_id": brewery_id,
        "cb_user": request.cb_user,
    })


@_login_required
def beer_edit(request, beer_id):
    try:
        beer = Beer.objects.get(pk=beer_id)
    except Beer.DoesNotExist:
        raise Http404("Beer not found")
    except Exception as e:
        messages.error(request, f"Failed to load beer: {e}")
        return redirect("beers:beer_list")

    if request.method == "POST":
        try:
            beer._data["name"] = request.POST.get("name", "").strip()
            beer._data["description"] = request.POST.get("description", "").strip() or None
            beer._data["abv"] = _safe_float(request.POST.get("abv", ""))
            beer._data["ibu"] = _safe_float(request.POST.get("ibu", ""))
            beer._data["srm"] = _safe_float(request.POST.get("srm", ""))
            beer._data["style"] = request.POST.get("style", "").strip() or None
            beer._data["category"] = request.POST.get("category", "").strip() or None
            beer._data["brewery_id"] = request.POST.get("brewery_id", "").strip() or None
            beer.save()
            messages.success(request, f"Beer '{beer.name}' updated.")
            return redirect("beers:beer_detail", beer_id=beer.pk)
        except Exception as e:
            messages.error(request, f"Failed to save: {e}")

    try:
        return render(request, "beers/beer_form.html", {
            "action": "Edit",
            "beer": beer,
            "beer_id": beer_id,
            "cb_user": request.cb_user,
        })
    except Exception as e:
        from django.http import HttpResponse

        return HttpResponse(f"Template render error: {type(e).__name__}: {e}", status=500)


@_login_required
def beer_delete(request, beer_id):
    try:
        beer = Beer.objects.get(pk=beer_id)
    except Beer.DoesNotExist:
        raise Http404("Beer not found")

    if request.method == "POST":
        name = beer.name
        beer.delete()
        messages.success(request, f"Beer '{name}' deleted.")
        return redirect("beers:beer_list")

    return render(request, "beers/confirm_delete.html", {
        "object_type": "Beer",
        "object_name": beer.name,
        "cancel_url": "beers:beer_detail",
        "cancel_id": beer_id,
        "cb_user": request.cb_user,
    })
