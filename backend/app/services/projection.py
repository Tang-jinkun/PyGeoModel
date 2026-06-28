from math import floor


def utm_epsg_from_lonlat(lon: float, lat: float) -> int:
    zone = floor((lon + 180) / 6) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone
