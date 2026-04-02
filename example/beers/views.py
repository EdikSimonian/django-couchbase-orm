from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from django_cb.queryset.q import Q

from .documents import Beer, Brewery


# ============================================================
# Auth views
# ============================================================


def login_view(request):
    if request.user.is_authenticated:
        return redirect("beers:home")

    if request.method == "POST":
        from django_cb.contrib.auth.backend import CouchbaseAuthBackend

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        backend = CouchbaseAuthBackend()
        user = backend.authenticate(request, username=username, password=password)
        if user is not None:
            # Manually set session
            request.session["_auth_user_id"] = user.pk
            request.session["_auth_user_backend"] = "django_cb.contrib.auth.backend.CouchbaseAuthBackend"
            messages.success(request, f"Welcome back, {user.get_short_name()}!")
            return redirect("beers:home")
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
    from django_cb.contrib.auth.models import User
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


def home(request):
    brewery_count = Brewery.objects.count()
    beer_count = Beer.objects.count()
    featured = list(Brewery.objects.order_by("name")[:12])
    cb_user = _get_current_user(request)

    return render(request, "beers/home.html", {
        "brewery_count": brewery_count,
        "beer_count": beer_count,
        "featured_breweries": featured,
        "cb_user": cb_user,
    })


def brewery_list(request):
    search = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))
    per_page = 20

    qs = Brewery.objects.order_by("name")
    if search:
        qs = qs.filter(name__icontains=search)

    total = qs.count()
    total_pages = (total + per_page - 1) // per_page
    breweries = list(qs[(page - 1) * per_page : page * per_page])

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


def beer_list(request):
    search = request.GET.get("q", "").strip()
    style = request.GET.get("style", "").strip()
    page = int(request.GET.get("page", 1))
    per_page = 20

    qs = Beer.objects.order_by("name")
    if search:
        qs = qs.filter(name__icontains=search)
    if style:
        qs = qs.filter(style=style)

    total = qs.count()
    total_pages = (total + per_page - 1) // per_page
    beers = list(qs[(page - 1) * per_page : page * per_page])

    styles = Beer.objects.raw(
        "SELECT DISTINCT d.style FROM `beer-sample`.`_default`.`_default` d "
        "WHERE d.type = 'beer' AND d.style IS NOT NULL ORDER BY d.style"
    )

    return render(request, "beers/beer_list.html", {
        "beers": beers,
        "search": search,
        "selected_style": style,
        "styles": [s["style"] for s in styles],
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
        brewery = Brewery(
            _id=request.POST.get("id", "").strip().replace(" ", "_").lower(),
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip() or None,
            city=request.POST.get("city", "").strip() or None,
            state=request.POST.get("state", "").strip() or None,
            country=request.POST.get("country", "").strip() or None,
            phone=request.POST.get("phone", "").strip() or None,
            website=request.POST.get("website", "").strip() or None,
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
        brewery._data["name"] = request.POST.get("name", "").strip()
        brewery._data["description"] = request.POST.get("description", "").strip() or None
        brewery._data["city"] = request.POST.get("city", "").strip() or None
        brewery._data["state"] = request.POST.get("state", "").strip() or None
        brewery._data["country"] = request.POST.get("country", "").strip() or None
        brewery._data["phone"] = request.POST.get("phone", "").strip() or None
        brewery._data["website"] = request.POST.get("website", "").strip() or None
        brewery._data["code"] = request.POST.get("code", "").strip() or None
        brewery.save()
        messages.success(request, f"Brewery '{brewery.name}' updated.")
        return redirect("beers:brewery_detail", brewery_id=brewery.pk)

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
        beer = Beer(
            _id=request.POST.get("id", "").strip().replace(" ", "_").lower(),
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip() or None,
            abv=float(request.POST["abv"]) if request.POST.get("abv") else None,
            ibu=float(request.POST["ibu"]) if request.POST.get("ibu") else None,
            srm=float(request.POST["srm"]) if request.POST.get("srm") else None,
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

    if request.method == "POST":
        beer._data["name"] = request.POST.get("name", "").strip()
        beer._data["description"] = request.POST.get("description", "").strip() or None
        beer._data["abv"] = float(request.POST["abv"]) if request.POST.get("abv") else None
        beer._data["ibu"] = float(request.POST["ibu"]) if request.POST.get("ibu") else None
        beer._data["srm"] = float(request.POST["srm"]) if request.POST.get("srm") else None
        beer._data["style"] = request.POST.get("style", "").strip() or None
        beer._data["category"] = request.POST.get("category", "").strip() or None
        beer._data["brewery_id"] = request.POST.get("brewery_id", "").strip() or None
        beer.save()
        messages.success(request, f"Beer '{beer.name}' updated.")
        return redirect("beers:beer_detail", beer_id=beer.pk)

    return render(request, "beers/beer_form.html", {
        "action": "Edit",
        "beer": beer,
        "beer_id": beer_id,
        "cb_user": request.cb_user,
    })


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
