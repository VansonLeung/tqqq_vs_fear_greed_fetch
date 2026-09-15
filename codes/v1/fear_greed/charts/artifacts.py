"""Atomic image/JSON publication to caller-owned output directories."""

import json
import os
import tempfile
from pathlib import Path


def save_figure(figure, destination):
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".chart-", suffix=".png", dir=destination.parent)
    os.close(descriptor)
    try:
        figure.savefig(temporary, format="png", dpi=100, facecolor=figure.get_facecolor())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination)


def save_json(value, destination):
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".report-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination)
