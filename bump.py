#!/usr/bin/env python
"""Bump la version du projet dans les fichiers qui la portent.

Usage: python bump.py 0.6.0
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# fichier -> motif encadrant la version (groupe 2 = le numéro seul)
TARGETS = {
    "pyproject.toml": re.compile(r'^(version = ")(\d+\.\d+\.\d+)(")', re.M),
    "webhook_receiver.py": re.compile(
        r'^(APP_VERSION = ")(\d+\.\d+\.\d+)(")', re.M
    ),
}

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def as_tuple(version):
    return tuple(int(part) for part in version.split("."))


def read_versions():
    """Retourne {fichier: (texte, version_actuelle)}, ou sort en erreur."""
    found = {}
    for name, pattern in TARGETS.items():
        text = (ROOT / name).read_text()
        match = pattern.search(text)
        if not match:
            sys.exit(f"erreur: pas de version trouvée dans {name}")
        found[name] = (text, match.group(2))
    return found


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} X.Y.Z")

    new = sys.argv[1].lstrip("v")
    if not SEMVER.match(new):
        sys.exit(f"erreur: '{new}' n'est pas une version X.Y.Z")

    found = read_versions()
    currents = {version for _, version in found.values()}
    if len(currents) > 1:
        details = ", ".join(f"{n}={v}" for n, (_, v) in found.items())
        sys.exit(f"erreur: versions désynchronisées ({details})")

    current = currents.pop()
    if as_tuple(new) <= as_tuple(current):
        sys.exit(f"erreur: {new} ne suit pas la version actuelle {current}")

    for name, (text, _) in found.items():
        bumped = TARGETS[name].sub(rf"\g<1>{new}\g<3>", text, count=1)
        (ROOT / name).write_text(bumped)

    print(f"{current} → {new}")
    for name in TARGETS:
        print(f"  {name}")
    print("\nMessage de commit (à copier-coller) :\n")
    print(f"feat: <description>, bump v{new}")


if __name__ == "__main__":
    main()
