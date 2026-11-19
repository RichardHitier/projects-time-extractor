"""Local: write the invoice and delivery note (.odt) of an invoice from
facturation.yml, then their PDF with LibreOffice.

    workon time_tracking && python dev/gen_facture_odt.py FA20261008 \
        TEMPLATE.odt OUTDIR

Template = a previous invoice of the same client (e.g. FA20260803_CL.odt).
The filling itself is `suivi.invoice_odt`, shared with the web app
(Projets › Factures, .odt only: no LibreOffice in the container).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import suivi  # noqa: E402

FACTURATION = "webhook-data/facturation.yml"


def main(invoice_id, template, outdir):
    facturation = suivi.load_facturation(FACTURATION)
    template_bytes = Path(template).read_bytes()
    outputs = []
    for kind in suivi.DOC_TITLES:
        out = Path(outdir) / f"{suivi.document_number(invoice_id, kind)}.odt"
        out.write_bytes(
            suivi.invoice_odt(template_bytes, facturation, invoice_id, kind))
        outputs.append(out)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(outdir), *map(str, outputs)], check=True)
    for out in outputs:
        print(out, out.with_suffix(".pdf"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
