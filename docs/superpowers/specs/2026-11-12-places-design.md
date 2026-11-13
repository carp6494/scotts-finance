# Places and addresses

Date: 2026-11-12. Status: approved.

## Goal

Every transaction shows where the money went: the store's street address when the bank sent one, the merchant's headquarters city when the purchase was online, and whatever the user typed when neither exists. Coordinates are stored when known so the map round can use them without touching this again.

## What the data already holds

Plaid sends a `location` block with each transaction (address, city, region, postal_code, country, lat, lon, store_number) and a `counterparties` list whose first entry carries the merchant's `website`. The app stores the whole raw record. Across the current database about 40 percent of rows carry a city and about 16 percent carry coordinates; in-store purchases are mostly covered, online purchases almost never.

## Data model

Additive columns on `transactions`:

| Column | Notes |
|---|---|
| place_address TEXT | Street line |
| place_city TEXT | |
| place_region TEXT | State or province code |
| place_postal TEXT | |
| place_country TEXT | |
| place_lat REAL, place_lon REAL | When known |
| place_store TEXT | Store number from Plaid |
| place_source TEXT | `plaid`, `hq`, `user`, or `none` |

New table `merchant_places`:

| Column | Notes |
|---|---|
| merchant_key TEXT PK | Same key as merchant memory: `lower(trim(coalesce(merchant_name, name)))` |
| name, address, city, region, postal, country, lat, lon | |
| kind TEXT | `user` |
| updated_at TEXT | |

Headquarters data is a static dict in `backend/places_seed.py` keyed by website domain, with name, city, region, country, and city-level coordinates for common merchants. It is generic public knowledge and ships with the app.

## Resolution order

`backend/places.py` exposes `fill(transaction_ids=None)`. For each row whose `place_source` is not `user`:

1. A `merchant_places` row for the merchant key wins, source `user`.
2. The Plaid location, if it has a city or coordinates, source `plaid`.
3. The headquarters dict by the counterparty website domain, else by a normalized merchant name match against the dict's names, source `hq`.
4. Else source `none`, all fields null.

`fill` runs at startup for rows with null `place_source`, after each sync on the touched ids, and after each import. It never raises; failures are logged.

## API

- Transaction list rows gain `place_line`, `place_source`, `place_lat`, `place_lon`, `place_city`, `place_region`. `place_line` is built server side: street plus city and region when there is a street; city and region when not; headquarters rows read `City, ST · headquarters`; user rows read what the user typed.
- `PATCH /api/transactions/{id}` accepts `place: {address, city, region, postal, country}`. It writes the row with source `user` and upserts `merchant_places` for the merchant key, then re-runs `fill` for every non-user row with that merchant key so the whole merchant moves at once. Passing `clear_place: true` deletes the merchant override and re-fills those rows from Plaid or headquarters.
- `GET /api/places/coverage` returns counts by source for the Settings-style readout on the Transactions page.

## Frontend

- `TxList`: a muted line under the category badge with a pin for a street or city, a building for headquarters, a pencil-free plain style for user entries. Clicking it opens a small inline form (address, city, state, zip) with Save and Clear. Save calls PATCH with `place`; Clear calls PATCH with `place: null`. The drawer's compact list shows city and state only, no form.
- Transactions page header: a small line "Places: N with an address, N headquarters, N unknown" from the coverage endpoint.

## Testing

- `places.py`: extract from a raw record; resolution order with a user override, a Plaid location, a domain match, a name match, and nothing; `fill` is idempotent and skips user rows; `place_line` formatting for each source.
- API: PATCH with place sets user source and moves sibling rows; PATCH with null reverts them.

## Out of scope

Geocoding from zip or city to coordinates for rows Plaid did not locate (needs a bundled dataset, decide at the map round), any network lookup, the 3D map.
