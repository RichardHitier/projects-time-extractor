"""Throwaway: fill an invoice .odt template from facturation.yml, then PDF.

    workon time_tracking && python dev/gen_facture_odt.py FA20261008 \
        TEMPLATE.odt OUTDIR

Template = a previous invoice of the same client (here FA20260803_CL.odt).
Replaces: invoice number, date, purchase order, quantity and HT of each lot
row (Tableau1), base HT / TVA / TTC (Tableau4); keeps everything else.
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

FACTURATION = "webhook-data/facturation.yml"
TVA_RATE = 0.20


def eur(value):
    """1620 → '1 620,00 €' (narrow no-break spaces like LibreOffice)."""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} €"


def set_cell(cell, value, text):
    """Table cell XML with its numeric value (if any) and shown text."""
    cell = re.sub(r'office:value="[^"]*"', f'office:value="{value:g}"', cell)
    return re.sub(r"(<text:p[^>]*>).*?(</text:p>)",
                  lambda m: m.group(1) + text + m.group(2), cell, count=1,
                  flags=re.S)


def fill(xml, invoice, commande, labels):
    number = f"{invoice['id']}_CL"
    # issue date = the date in the number (FA20261008 → 08/10/2026)
    day = f"{invoice['id'][2:6]}-{invoice['id'][6:8]}-{invoice['id'][8:10]}"
    date = f"{day[8:10]}/{day[5:7]}/{day[:4]}"
    # number: everything after " n° : " up to the end of the paragraph
    # (French typography: no-break space before the colon)
    xml = re.sub(r"(n°[\s\u00a0]+:[\s\u00a0]*</text:span>).*?(</text:p>)",
                 rf'\1<text:span text:style-name="T10">{number}</text:span>\2',
                 xml, count=1, flags=re.S)
    xml = re.sub(r"(Date[\s\u00a0]+:[\s\u00a0]*).*?(<text:line-break/>Réf)",
                 rf"\g<1>{date}\2", xml, count=1, flags=re.S)
    xml = re.sub(r"(Bon de Commande : <text:span[^>]*>)[^<]*",
                 rf"\g<1>{commande['ref']}", xml, count=1)

    tjm = float(commande["tjm"])
    lots = invoice.get("lots") or {}

    def lot_row(row):
        cells = re.findall(r"<table:table-cell.*?</table:table-cell>", row,
                           re.S)
        designation = re.sub(r"<[^>]+>", "", cells[0])
        code = next((c for c, label in labels.items()
                     if label in designation), None)
        if code is None:          # header row
            return row
        days = float(lots.get(code, 0))
        new = [cells[0], set_cell(cells[1], days, f"{days:g}"),
               cells[2], set_cell(cells[3], days * tjm, eur(days * tjm))]
        for old, cell in zip(cells, new):
            row = row.replace(old, cell, 1)
        return row

    def table(name, edit):
        nonlocal xml
        start = xml.index(f'table:name="{name}"')
        end = xml.index("</table:table>", start)
        xml = xml[:start] + edit(xml[start:end]) + xml[end:]

    table("Tableau1", lambda t: re.sub(
        r"<table:table-row.*?</table:table-row>",
        lambda m: lot_row(m.group(0)), t, flags=re.S))

    ht = float(invoice["jours"]) * tjm
    totals = {0: (ht, eur(ht)), 2: (ht * TVA_RATE, eur(ht * TVA_RATE)),
              3: (ht * (1 + TVA_RATE), eur(ht * (1 + TVA_RATE)))}

    def totals_row(t):
        rows = re.findall(r"<table:table-row.*?</table:table-row>", t, re.S)
        cells = re.findall(r"<table:table-cell.*?</table:table-cell>",
                           rows[1], re.S)
        new_row = rows[1]
        for i, (value, text) in totals.items():
            new_row = new_row.replace(cells[i], set_cell(cells[i], value,
                                                          text), 1)
        return t.replace(rows[1], new_row, 1)

    table("Tableau4", totals_row)
    return xml


def main(invoice_id, template, outdir):
    data = yaml.safe_load(open(FACTURATION, encoding="utf-8"))
    invoice = next(f for f in data["factures"] if f["id"] == invoice_id)
    commande = next(c for c in data["commandes"]
                    if c["nom"] == invoice["commande"])
    labels = data["lots"][commande["projet"]]

    out = Path(outdir) / f"{invoice_id}_CL.odt"
    with zipfile.ZipFile(template) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "content.xml":
                content = fill(content.decode("utf-8"), invoice, commande,
                               labels).encode("utf-8")
            # mimetype must stay first and uncompressed (ODF rule)
            dst.writestr(item, content, compress_type=item.compress_type)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(outdir), str(out)], check=True)
    print(out, out.with_suffix(".pdf"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
