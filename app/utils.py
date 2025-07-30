from datetime import datetime

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {"png", "jpg", "jpeg"}

def validate_iso8601(timestamp):
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False

MONTH_NAMES = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}