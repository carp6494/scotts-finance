import geo
import overture


def near(spot, lat, lon, tol=0.5):
    return spot is not None and abs(spot[0] - lat) < tol and abs(spot[1] - lon) < tol


def test_zip_lookup():
    assert near(geo.by_zip("10001"), 40.75, -73.99)
    assert near(geo.by_zip("10001-1234"), 40.75, -73.99)
    assert near(geo.by_zip(98101), 47.61, -122.33)
    assert geo.by_zip("00000") is None
    assert geo.by_zip("") is None
    assert geo.by_zip(None) is None
    assert geo.by_zip("ABCDE") is None


def test_city_lookup_is_the_center_of_its_zips():
    assert near(geo.by_city("Seattle", "WA"), 47.61, -122.33)
    assert near(geo.by_city("seattle", "wa"), 47.61, -122.33)
    assert near(geo.by_city("Seattle", "Washington"), 47.61, -122.33)
    assert geo.by_city("Seattle", "FL") is None
    assert geo.by_city("", "WA") is None
    assert geo.by_city(None, None) is None


def test_saint_and_fort_spellings():
    assert near(geo.by_city("St. Louis", "MO"), 38.63, -90.24)
    assert near(geo.by_city("Saint Louis", "MO"), 38.63, -90.24)
    assert near(geo.by_city("Ft Worth", "TX"), 32.75, -97.33)


def test_city_without_state():
    assert near(geo.by_city("Los Gatos"), 37.23, -121.96)  # only one state has it
    assert near(geo.by_city("Brooklyn"), 40.65, -73.95)  # several do; New York has the most zips
    assert near(geo.by_city("Springfield", None, "IL"), 39.8, -89.65)  # the preferred state wins
    assert near(geo.by_city("Brooklyn", None, "WY"), 40.65, -73.95)  # preferred state has none, so most zips
    assert geo.by_city("Xyzzyville") is None
    assert geo.by_city("Seattle", "Nowhere") is None  # a state that does not exist is not a missing state


def test_state_helpers():
    assert geo.state_code("co") == "CO" and geo.state_code("Colorado") == "CO" and geo.state_code("Narnia") is None
    lo_lat, hi_lat, lo_lon, hi_lon = geo.state_box("CO")
    assert 36 < lo_lat < 38 and 40 < hi_lat < 42 and -110 < lo_lon < -108 and -103 < hi_lon < -101
    assert geo.state_box("ZZ") is None


def test_norm_name():
    n = overture.norm_name
    assert n("SQ *The Joe's BBQ #12") == "joesbbq"
    assert n("Joes BBQ") == "joesbbq"
    assert n("TST* Blue Door Cafe, LLC") == "bluedoorcafe"
    assert n("A&W") == "aandw"
    assert n("Studio 54") == "studio"  # trailing number goes, like a store number
    assert n("7") == "7"
    assert n(None) == ""
    assert n("Island Grill - K") == "islandgrill"
    assert n("Circle K") == "circlek"
