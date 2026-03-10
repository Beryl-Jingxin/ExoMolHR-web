import os
import time
from datetime import datetime
from zipfile import ZipFile
from django.conf import settings


def make_hex_timestamp():
    """Return the filestem for output file archives."""

    if 0 and settings.DEBUG:
        # If we're debugging, use a single filestem, not a timestamp
        return "test"

    # Integer timestamp: the number of seconds since 00:00 1 January 1970
    ts_int = int(time.mktime(datetime.utcnow().timetuple()))
    # Make the timestamp from the hex representation of ts_int, stripping
    # off the initial '0x' characters:
    filestem = hex(ts_int)[2:]
    return filestem

def make_decimal_timestamp():
    """Return a decimal timestamp for output filenames."""

    if 0 and settings.DEBUG:
        return "test"

    tstamp = datetime.utcnow()
    return f"{tstamp:%Y%m%d%H%M%S}"


def make_zip_bundle(output_filename, output_files):
    output_filepath = settings.RESULTS_DIR / output_filename

    with ZipFile(output_filepath, "w") as zipfile:
        for output_filename in output_files:
            sys_filename = settings.RESULTS_DIR / output_filename
            zipfile.write(sys_filename, output_filename)

    archive_size = os.stat(output_filepath).st_size

    return archive_size
