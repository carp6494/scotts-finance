# Map round: design

Date: 2026-11-13

## Goal

Show where the money went on a 3D map. Give every transaction the most precise location that free data allows. Everything works offline after two one-time downloads.

## Decisions made with the owner

- Zip and city coordinates come from the GeoNames postal code file for the United States. License CC BY 4.0. The whole file ships in the repo.
- Local business addresses come from Overture Maps Places. The extract covers the owner's home area, so it stays in `data\` and is never committed. The repo holds only the download script.
- Shop icons come from each shop's own website. This is a new outbound call. It sends no transaction data. A switch on the Settings page turns it off.
- The Map page has two views: a United States map and a world globe.
- No transaction address is shortened or dropped. Each source only adds detail.

## Part A: coordinates from GeoNames

- `backend/geo/US.txt` is the unmodified GeoNames file. `backend/geo/GEONAMES-README.txt` is its readme. `README.md` credits GeoNames with a link.
- `backend/geo.py` loads the file on first use. `by_zip(postal)` returns the zip's coordinates. `by_city(city, region)` returns the mean of that city's zips. City names compare without case or punctuation, and "St" matches "Saint".
- New column `transactions.place_precision`: `exact`, `zip`, `city`, `hq`, or empty.
- `places.resolve` gains a last step. A row with a place but no coordinates gets them from its zip, else from its city and state. Rows with no country or with `US` qualify.
- Precision rules: coordinates from the bank or typed by the owner are `exact`. A headquarters row is `hq`.

## Part B: local business lookup from Overture

- `scripts/fetch_places.py --states XX` downloads Overture places inside the bounding box of the named states. The box comes from the GeoNames file. It writes `data/overture.db`, a SQLite file with one `places` table. It needs the `overturemaps` package, listed in `requirements-tools.txt`. The app itself does not import it.
- `backend/overture.py` opens `data/overture.db` read-only when it exists. With no file, every lookup returns nothing and the app works as before.
- Matching uses the normalized merchant name. Normalizing lowercases, drops punctuation, drops trailing store numbers, and drops "the", "inc", "llc", "co".
  - Bank gave a city: accept when exactly one place in that city has the same name.
  - Bank gave no place: accept when exactly one place in the whole extract has that name, the purchase was not made online, and the merchant has no known headquarters.
  - Several matches: accept nothing. The city center or headquarters stays.
- A match sets the street address, city, state, zip, coordinates, and website. Source is `overture`. Precision is `exact`.
- A bank row that has coordinates but no street address, or the reverse, keeps what the bank sent and takes only the missing part from the match. Its source stays `plaid`.
- Order in `places.resolve`: owner override, bank location helped by an Overture match in the same city, headquarters, Overture match by name alone, none.
- A city that came with no state uses the state most of the owner's purchases are in, when that state has such a city. Otherwise it uses the state where that city has the most zips.
- New column `transactions.place_website` holds the website from a match.

## Part C: shop icons from websites

- `logos.merchant_logo` gains a third choice after ticker logos and Plaid logos: the icon of the merchant's website. The website is Plaid's `website` field or `place_website`.
- `backend/site_icons.py` fetches the home page over HTTPS, reads the icon links, picks the largest, and falls back to `/favicon.ico`. It saves the image under `data/logos/sites/`.
- Safety: HTTPS only, public host names only, no IP addresses, at most 3 redirects, 10 second timeout, 300 KB cap, image types only. One try per domain. A failed domain is recorded and not tried again for 30 days.
- The request carries a generic user agent and nothing about the owner or the purchase.
- Setting `site_icons`, default on. Settings page row: "Get shop icons from their websites".

## Part D: map API

- `GET /api/map` takes `account_id`, `cat_id`, `q`, `start`, `end`, `hq`. It returns spending grouped by spot.
- A spot is latitude and longitude rounded to 4 places. Each spot has city, state, country, precision, total, count, and its top 5 merchants.
- Only spending counts: positive amounts, not transfers, not excluded. Headquarters spots are left out unless `hq=1`.
- The response also reports how many spending rows have no coordinates and their total.
- `GET /api/transactions` gains `spot=lat,lon` to list one spot's rows.

## Part E: Map page

- New sidebar entry "Map". The page loads its 3D code only when opened.
- New npm packages, all bundled: `three`, `d3-geo`, `topojson-client`, `us-atlas`, `world-atlas`, `globe.gl`. No tiles, textures, or fonts load from the network.
- United States view: state outlines on a tilted plane, drawn with three.js. A column stands on each spot. Height follows the square root of the total. Drag rotates, scroll zooms.
- World view: a globe with country outlines and the same columns.
- Color shows precision. Exact is the accent color. Zip and city are lighter. Headquarters is purple.
- Hover shows city and total. Click opens a panel with the top merchants and the transaction list for that spot.
- Controls: view switch, date range, account, category, and "Show online purchases at headquarters", off by default.
- A line under the map says how many purchases have no location.

## Security

- `docs/SECURITY.md` gains a row for the website icon fetch and its limits.
- The Overture extract and all icons live under `data\`, which is gitignored.
- No new route sits under `/api/auth/`.

## Tests

- `test_geo.py`: zip lookup, city lookup, Saint handling, unknown inputs.
- `test_places.py`: precision labels, fill from zip and city, Overture order and the three match rules, using a small temporary Overture file.
- `test_site_icons.py`: link parsing, host rules, size cap, retry window. No network.
- `test_map.py`: grouping, filters, headquarters switch, unplaced count, `spot` filter.

## Changes after the first build

The owner looked at the first build and asked for these. Where they differ from the parts above, this section wins.

- Lookup: a longer or shorter form of the name also counts, and the search widens to about 10 km around the city center. A match still needs exactly one fit.
- New source `history`: a merchant with no place borrows the one spot its other purchases agree on.
- New precision `likely`: when a chain has several branches in the city, the app picks the branch nearest the middle of the owner's bank-located purchases. The place line starts with "likely". Typing a place on any row replaces the guess for that merchant.
- A bar is one business, not one spot. `GET /api/map` returns one point per business per spot, with `id`, `name`, `address`, `show_lat` and `show_lon`. Businesses that share a point stand in a spiral around it. `GET /api/transactions` gains `merchant`, `start` and `end`.
- Bars shrink as the map zooms in.
- The World view is a heatmap with small dots that can be clicked. It has no columns.
- The Map page has a Style row: Outline, Satellite, Hybrid, Terrain. Outline is the three.js map and loads nothing from the network. The other three use MapLibre GL JS in `TileMap.jsx`, with a "Terrain height" slider, elevation colors, and a "3D buildings" checkbox.
- Map squares come through `backend/tiles.py`, never straight from the browser. It allows three services: USGS for photos and labels, Terrain Tiles on AWS Open Data for elevation, OpenFreeMap for buildings. Squares are saved in `data/tiles`. Each service has a switch on the Settings page under "Map data". USGS is on by default. The other two are off by default.
- Transaction dates show the year. A transaction with no logo shows its category icon on a dark tile.
- Added tests: `test_tiles.py`, and business grouping and the `merchant` filter in `test_map.py`.

## Out of scope

Postal files for other countries, live geocoding services, paid place services, editing spots on the map.
