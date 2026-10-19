"""Shared set-up: local ixmp platform, GAMS location and paths.

message_ix stores scenarios on an ixmp platform. Here it is a local HSQLDB
database in db/ (JDBC backend), which needs a Java runtime (JAVA_HOME) and a
full GAMS installation with its Java API (GAMS_SYSDIR, or `gams` on PATH).
Without a GAMS licence, GAMS runs in demo mode, which is enough for Westeros.
"""
import os
import shutil
from pathlib import Path

import ixmp

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "westeros"
RESULTS = ROOT / "results"
MODEL = "Westeros Electrified"
COUNTRY = "Westeros"


def gams_sysdir():
    if os.environ.get("GAMS_SYSDIR"):
        return Path(os.environ["GAMS_SYSDIR"])
    exe = shutil.which("gams")
    if exe:
        return Path(exe).resolve().parent
    raise RuntimeError("GAMS not found: set GAMS_SYSDIR to the GAMS system directory")


def platform():
    """Local HSQLDB platform inside the repository (db/ is not committed)."""
    if not os.environ.get("JAVA_HOME"):
        raise RuntimeError("set JAVA_HOME to a Java runtime (11 or newer)")
    sysdir = str(gams_sysdir())
    if sysdir not in os.environ["PATH"].split(os.pathsep):
        os.environ["PATH"] = sysdir + os.pathsep + os.environ["PATH"]
    DB.parent.mkdir(exist_ok=True)
    return ixmp.Platform(backend="jdbc", driver="hsqldb", path=DB)
