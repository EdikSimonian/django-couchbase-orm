# Couchbase Capella App Services Setup

Step-by-step guide to configure App Services for BrewSync mobile sync.

## Prerequisites

- Couchbase Capella cluster with `beer-sample` bucket
- Django OIDC provider deployed (verify: `https://django-couchbase-orm-production.up.railway.app/o/.well-known/openid-configuration/`)

## 1. Enable App Services

1. Go to **Capella Console** → your project → cluster
2. Click **App Services** tab
3. Click **Create App Endpoint**
4. Select the `beer-sample` bucket
5. Name: `brewsync`
6. Choose a compute size (smallest is fine for demo)

## 2. Configure OIDC Authentication

1. In the App Endpoint, go to **Security** → **Authentication**
2. Click **Add Provider** → **OpenID Connect**
3. Configure:
   - **Name**: `django`
   - **Issuer**: `https://django-couchbase-orm-production.up.railway.app/o`
   - **Client ID**: `brewsync-ios`
   - **Discovery URL**: `https://django-couchbase-orm-production.up.railway.app/o/.well-known/openid-configuration/`
   - **Register**: Disabled (users pre-registered via Django)
4. Under **Role Mapping**:
   - **Roles Claim**: `groups`
   - Map claim value `admin` → Sync Gateway role `admin`

## 3. Configure Collections

Map these Django-created collections in the App Endpoint:

| Collection | Scope | Description |
|---|---|---|
| `beers_beer` | `_default` | Beer documents |
| `beers_brewery` | `_default` | Brewery documents |
| `beers_rating` | `_default` | User rating documents |

## 4. Sync Functions

Set per-collection sync functions:

### beers_beer

```javascript
function sync(doc, oldDoc, meta) {
  channel("beers");

  // All authenticated users can read
  access("*", "beers");

  // Only admin role can write
  requireRole("admin");
}
```

### beers_brewery

```javascript
function sync(doc, oldDoc, meta) {
  channel("breweries");
  access("*", "breweries");
  requireRole("admin");
}
```

### beers_rating

```javascript
function sync(doc, oldDoc, meta) {
  channel("ratings");
  access("*", "ratings");

  // Users can only write their own ratings
  if (oldDoc && oldDoc.username !== doc.username) {
    throw({forbidden: "Cannot modify another user's rating"});
  }
  requireUser(doc.username);
}
```

## 5. Channel Access

Configure default channel access for authenticated users:
- All users: `beers`, `breweries`, `ratings` channels

## 6. Verify

Get the App Services endpoint URL (shown in Capella console, e.g., `wss://xxx.apps.cloud.couchbase.com:4984/brewsync`).

Test OIDC redirect:
```bash
curl -v https://<app-services-url>/_oidc?provider=django
# Should redirect to Django's /o/authorize/
```

## 7. iOS App Configuration

Use the App Services endpoint URL in the iOS app's `ReplicatorManager.swift`:

```swift
let url = URL(string: "wss://<app-services-url>:4984/brewsync")!
let endpoint = URLEndpoint(url: url)
```

The iOS app authenticates via OIDC (ASWebAuthenticationSession → Django → tokens), then passes the session token to the Couchbase Lite replicator.

## Document Format

Documents synced between Django and iOS share this format:

### Beer
```json
{
  "id": 1,
  "doc_type": "beer",
  "name": "Hop Highway IPA",
  "abv": 6.8,
  "ibu": 65,
  "style": "IPA",
  "brewery_id": 1,
  "description": "...",
  "image_url": "",
  "avg_rating": 4.2,
  "rating_count": 5,
  "created_at": "2026-04-02T...",
  "updated_at": "2026-04-03T..."
}
```

### Rating
```json
{
  "id": "rating::1::3",
  "doc_type": "rating",
  "beer_id": 1,
  "user_id": 3,
  "username": "john",
  "score": 4,
  "created_at": "2026-04-03T..."
}
```
