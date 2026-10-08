"""Script jetable : ventilation par lot des factures émises (FA*.odt).

Lit le 2e tableau de chaque facture (Désignation | Quantité | PU | HT) et
imprime, pour facturation.yml, le catalogue des lots par répertoire et les
`lots: {...}` de chaque facture. Code du lot = préfixe de la désignation avant
« : », espaces remplacés par « _ » (« WP 1 » → WP_1, « JUICE E2 » →
JUICE_E2).

    workon time_tracking && python dev/extract_lots_odt.py DIR [DIR ...]
"""
import glob
import os
import re
import sys

from odf import table
from odf.opendocument import load


def _text(node):
    return "".join(
        n.data if n.nodeType == n.TEXT_NODE else _text(n)
        for n in node.childNodes
    )


def invoice_lines(path):
    """[(code, libellé, jours)] du tableau des prestations de la facture."""
    lines_table = load(path).getElementsByType(table.Table)[1]
    lines = []
    for row in lines_table.getElementsByType(table.TableRow)[1:]:
        cells = [_text(c).strip()
                 for c in row.getElementsByType(table.TableCell)]
        if not cells or not cells[1]:
            continue
        code, _, label = cells[0].partition(":")
        code = re.sub(r"\s+", "_", (code if label else cells[0]).strip())
        days = float(cells[1].replace(",", "."))
        days = int(days) if days.is_integer() else days
        lines.append((code, label.strip(), days))
    return lines


def main(dirs):
    for directory in dirs:
        catalog = {}
        print(f"# {directory}")
        for path in sorted(glob.glob(os.path.join(directory, "FA*.odt"))):
            invoice_id = re.match(r"FA\d{8}", os.path.basename(path)).group(0)
            lines = invoice_lines(path)
            for code, label, _ in lines:
                catalog[code] = label
            lots = ", ".join(f"{code}: {days}" for code, _, days in lines)
            print(f"{invoice_id}: {{{lots}}}")
        for code, label in catalog.items():
            print(f'    {code}: "{label}"')
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
