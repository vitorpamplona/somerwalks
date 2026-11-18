# Bus trips and Somerville's pulse (`analysis/bus-trips/`)

Agent guide for two pages built by one script. Start with the root [`AGENTS.md`](../../AGENTS.md). What the pages show, the method and its limits are in [`README.md`](README.md); keep it current when what a page shows changes.

- **Where bus riders go** (`docs/bus-trips.html`, somerwalks.org/bus-trips.html): every route with a stop in Somerville, drawn whole through the towns it serves. Pick a stop to see about where its riders get off (or where riders getting off there got on), weekday, Saturday or Sunday, and what's at the stop.
- **Somerville's pulse** (`docs/bus-pulse.html`, somerwalks.org/bus-pulse.html, a tile on the home page): a weekday played back on a canvas, every bus trip moving along its route and every Red, Orange, Green and Blue Line train on the map along its line, stops and stations flashing as riders get on and off. `#lights` opens its Holiday lights look.

Both are **estimates**, not MBTA data, and say so on the page.

## Files and build

| File | What it is |
|---|---|
| `build.py` | Downloads everything (cached in `../../.cache/`; every build still fetches the MBTA's small feed list, so it needs the network), estimates stop-to-stop riders, writes both pages. Python standard library only. `npm run trips` from the repo root. |
| `trips_template.html` | The "Where bus riders go" page: map, sidebar, interaction. `build.py` replaces `/*DATA*/null` with the data. |
| `pulse_template.html` | The pulse page: canvas animation, clock, counts, waveform, controls. Same `/*DATA*/null` placeholder. |
| `output/trips.html`, `output/pulse.html` | The built pages (self-contained, open in any browser). |
| `../../docs/bus-trips.html`, `../../docs/bus-pulse.html` | Copies on the public site, made by `build.py`. **Never edit them**; edit the template and rebuild. |
| `../../docs/bus-trips-basemap.json` | The street map under "Where bus riders go", written by `basemap()` beside the page (about 1.1 MB, loaded after the map draws). Commit it with the page. |
| `../osm_base.py` | Shared with `analysis/transit-trends/`: Overpass in tiles (`overpass_tiles()`), simplifying and packing, the street layers (`layers()`), buildings (unused here). |

The build prints a summary line per page (stops, routes, riders a day, page size; trips matched to the schedule). Check it didn't change unexpectedly. The pages run with no server; to test, `npm run dev` and open `/bus-trips.html` or `/bus-pulse.html` (desktop and 390 px).

## Data and how it's joined

- **Riders:** the MBTA's bus ridership by trip, season, route and stop, newest Fall season (Fall 2025): average boardings and alightings per scheduled trip and stop (`trips()`). Routes: every route with a stop in Somerville in `docs/snow/data/bus-stops.json` (`somerville_routes()`).
- **Schedule:** the last GTFS feed of the same season from the MBTA's archive (`gtfs()`), not today's API (routes change: no CT2 today). Stops, shapes, directions, subway lines and stations come from it.
- **The estimate** (`estimate()`): trip by trip, everyone on board is equally likely to get off at each stop; the totals by stop are the MBTA's.
- **Hours** (`by_hour()`): the trip's start time plus the schedule's usual minutes to that stop; per stop, and per stop and route-direction (`hoursRd` in the data, only at stops with more than one bus, so the chart can follow the bus picked).
- **Pulse** (`pulse()`): every weekday trip with its own scheduled times, matched to the schedule by route, direction and start time (954 of 1,090; the rest use the usual minutes); trips logged before 3 a.m. (start time under 180) go at the end of the service day. Trips sharing route, direction, stops and times share a pattern.
- **Trains** (`trains()`, in the pulse only): every Red, Orange, Green and Blue Line trip (`LINES`) running on a typical weekday (the first Wednesday a week into the feed: `calendar.txt` plus that day's `calendar_dates.txt` exceptions; 2,436 trips on Dec 3, 2025), station by station (child stops → `parent_station`) at its scheduled times, cut to the stretches inside the map; trips sharing line, direction, stations and minutes (to the quarter) share a pattern. The track between two stations is a piece of the trip's shape (`piece()`, from the platforms' positions; 6 of 184 station pairs have no piece and are straight). Riders: the MBTA's rail ridership by station, line, direction and hour (item `6494749a…`, Fall 2025 CSV, cached `mbta-rail-ridership-fall-2025.csv`): weekday `total_ons` and `total_offs` over `number_service_days`, and `average_flow` (riders on board leaving the station); `dir_id` NB/SB/EB/WB matched to the schedule's `directions.txt`; hours 0–3 a.m. are the end of the service day (24–27). The page splits each hour's riders evenly among the trains that stop there that hour, line and direction (`TEV`, train loads): an estimate, and the page says so.
- **What's at the stop:** MBTA PATI (ADA status Jan 2024, amenities 2017; bench rows merged per stop) and OpenStreetMap (matched by `ref`, else nearest within 30 m; each value's year from the node's edit history, cached in `.cache/osm-hist/`). `features()` in `trips_template.html` decides each item's state (yes / no / no data) for both the tiles and the map, from the newest source.
- **Map layers:** MassGIS town outlines and MassDEP water (POLY_CODE 1, 6, 8; town lines run down the middle of the Charles and the Mystic, so water is its own layer).
- **Street map (`basemap()`, Where bus riders go only):** OpenStreetMap through Overpass in 4 × 4 tiles over the map's box (`.cache/bus-trips-osm-base.json`), made into layers by `osm_base.layers()`: major and minor streets, footpaths and bike paths only within Somerville's box plus about 250 m, commuter rail, green land, water, street names everywhere (one per 300 m per street). No buildings: the owner wants the streets without the housing map's layers, even zoomed in. The page paints a canvas (`#base`, `paintBase()`) under the SVG: towns, green, OSM water, MassDEP water, town lines, then paths (under 5 m a pixel), rail, minor and major streets (wider as you zoom), and street names under 2.6 m a pixel where they don't overlap. Towns and water moved from the SVG to this canvas. It repaints on every view change and when the map is resized (a `ResizeObserver`: the map shrinks on phones once a stop is picked), from the SVG's own screen matrix, so the two always line up. **Somerville's pulse has no street map, on purpose**: it's an animation, better without.

## Gotchas

- **Overpass servers are busy and some are stale.** In Nov 2026 overpass-api.de reset connections from the build machine, maps.mail.ru answered small queries but timed out (504) on big ones, and overpass.kumi.systems answered with data months old (May 2026, and once bus stops as they were in 2024, dropping a year of volunteers' bench, bin and lighting edits). So every Overpass query is in tiles (`osm_base.overpass_tiles()`, the stop details too, 3 × 3), each tile tried on each server in turn, an answer whose data is over 7 days old is refused (`stale()`), and tiles fetched so far are kept in a `.part` file: a build after a failure fetches only the missing tiles, and the cache is written only when every tile is in. The streets took about 1.5 hours the first time. Compare the stop details with the previous page before committing ("OpenStreetMap: N matched, N with a shelter tag").
- **Route "194" is the 89/93.** The ridership file says 194; the schedule says `8993`. `SCHEDULE_ID` maps it. The CT2 is `747` in the API and ridership files.
- **Bennett Alley** (a ridership stop id no schedule has, before Harvard's upper busway) is counted at the next stop (`merge_unknown()`).
- **Friday** is in the ridership file on its own and left out; "Weekday" is `Wkdy`.
- **Stops with under 1 rider a day** aren't highlighted or listed (`MIN` in the template); pairs under 0.05 a day are dropped (`MIN_RIDERS`).
- **Colors mean one thing:** orange (`#E36F28`/`#FF8A3D`) getting on, blue (`#4F98DE`) getting off, in bars, lists, rings and charts. In the pulse's Holiday lights look, red and green.
- **Route colors** come from `COLORS` by route index; they're the map's palette, not MBTA colors.
- **Data size:** both pages carry their data inline (about 1 MB and 620 KB; the trains are about 150 KB of the pulse). Adding per-stop or per-trip data grows them fast; measure (the build prints the size). The street map is a separate file (about 1.1 MB), fetched after the map draws.

## The "Where bus riders go" sidebar

Since Nov 2026 (prototype D of a design review): search; the stop's name and its routes count; day; a get on / get off switch that carries both counts; then one section per question: **When it's busy** (riders on and off by hour, follows the bus picked), **Which bus** (a row per route and direction with a bar as a share of all riders here; tap to filter; "Every bus" resets; changing the day or direction resets it), **Where they get off** / **Where they got on** (top 5, then all; route badges only when every bus is shown), **At this stop** (icon tiles; tap one, or its icon in the map's bottom toolbar, to find every stop with it). Before a stop is picked: the busiest stops in Somerville. On phones the map shrinks to 45% of the screen once a stop is picked. The address keeps the view (`#stop=5104&day=Sat&show=on`).

## The pulse page

Canvas layers: `base` (map, redrawn on pan/zoom), `trail` (fading bus trails), `top` (glows, rings, buses, cleared every frame). The clock runs in minutes of the day (`T`, 4:00 a.m. to 2:00 a.m.); speeds 1×/2×/5× are 6/12/30 minutes a second. Events (a bus at a stop with riders on or off) are sorted once and fired as the clock passes them; each stop's glow decays over about 10 minutes of the day. Trains (`TT`, `TEV`, `tOn`/`tOff`, `tseg()`) run on the same clock: dots in their line's color sized by riders on board, a faint trail, and stations glowing orange and blue on a gentler scale than bus stops (radius 4 + 1.05√riders, alpha up to .55: Davis gets about 1,000 riders an hour). Hover a station for its last hour. The counts keep the buses' three and add "on a train now" (trains on the map); the waveform stays buses only. Buttons: Buses (hide dots and trails), Trains (hide trains, station glows and rings; the Holiday lights look turns them off with the buses), Holiday lights (`THEMES.lights`: red/green, warm-white bulbs that twinkle, gold outline, snow; buses off; `#lights` in the address). With `prefers-reduced-motion` it starts paused, and there's no snow or twinkling. `npm run lights` drives this page frame by frame to make the cards-gallery GIF (see [`scripts/AGENTS.md`](../../scripts/AGENTS.md)); if you rename `seek`, `advance`, `draw`, `hud`, `view`, `HOME`, `makeSnow` or `viewChanged`, update `scripts/render-lights.mjs`.

## Open questions

No official data on shelters or real-time signs (questions 58–61 in [`research/questions.md`](../../research/questions.md)). Volunteers can fix stop details on OpenStreetMap (each stop has an "Edit on OSM" link); the next build picks them up.
