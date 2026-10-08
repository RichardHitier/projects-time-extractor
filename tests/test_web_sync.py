import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli

YML = b"commandes:\n  - {nom: speasy, projet: speasy, debut: '2025-10-01'}\n"


def test_sync_facturation_writes_a_new_file(tmp_path):
    dest = tmp_path / "webhook-data" / "facturation.yml"
    message = cli.sync_facturation(YML, str(dest), str(tmp_path / "bckp"))
    assert dest.read_bytes() == YML
    assert "écrit" in message
    assert not (tmp_path / "bckp").exists()


def test_sync_facturation_backs_up_a_different_local_file(tmp_path):
    dest = tmp_path / "facturation.yml"
    dest.write_bytes(b"commandes: []\n")
    bckp = tmp_path / "bckp"
    message = cli.sync_facturation(YML, str(dest), str(bckp))
    assert dest.read_bytes() == YML
    (backup,) = bckp.iterdir()
    assert backup.read_bytes() == b"commandes: []\n"
    assert "mis à jour" in message


def test_sync_facturation_leaves_an_identical_file_alone(tmp_path):
    dest = tmp_path / "facturation.yml"
    dest.write_bytes(YML)
    message = cli.sync_facturation(YML, str(dest), str(tmp_path / "bckp"))
    assert "inchangé" in message
    assert not (tmp_path / "bckp").exists()


def test_sync_facturation_refuses_invalid_content(tmp_path):
    dest = tmp_path / "facturation.yml"
    dest.write_bytes(YML)
    for data in (b"<html>erreur</html>", b"commandes: [\n", b"factures: []\n"):
        message = cli.sync_facturation(data, str(dest), str(tmp_path / "bckp"))
        assert "rien écrasé" in message
        assert dest.read_bytes() == YML
    assert not (tmp_path / "bckp").exists()


def test_netrc_opener_adds_basic_auth_for_the_url_host(tmp_path):
    rc = tmp_path / "netrc"
    rc.write_text("machine timer.example.org login richard password s3cret\n")
    rc.chmod(0o600)
    opener = cli._netrc_opener("https://timer.example.org/api/csv", str(rc))
    (handler,) = [h for h in opener.handlers
                  if isinstance(h, cli.urllib.request.HTTPBasicAuthHandler)]
    assert handler.passwd.find_user_password(
        None, "https://timer.example.org/api/csv") == ("richard", "s3cret")


def test_netrc_opener_without_entry_has_no_auth(tmp_path):
    rc = tmp_path / "netrc"
    rc.write_text("machine other.example.org login a password b\n")
    rc.chmod(0o600)
    for path in (str(rc), str(tmp_path / "absent")):
        opener = cli._netrc_opener("https://timer.example.org/api/csv", path)
        assert not [h for h in opener.handlers
                    if isinstance(h, cli.urllib.request.HTTPBasicAuthHandler)]
