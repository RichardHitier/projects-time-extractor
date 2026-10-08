# SPEC — https
Date : 2026-10-08
Statut : terminé (v0.36.0) — HTTPS et mot de passe par Caddy (VPS)

## Objectif (une phrase)
`https://timer.co-libri.org` servi par Caddy (déjà installé sur le VPS pour
apnee), avec mot de passe ; le webhook Pomofocus reste en HTTP sur le port 80.

## Pourquoi pas nginx + certbot
Première tentative (A1 certbot, A2 nginx sur 443, v0.35.0) : le port 443 est
tenu par Caddy (`~/01DEV/apnee/Caddyfile`), nginx n'a pas démarré, prod coupée
~2 min, A2 annulé. Caddy laisse volontairement le 80 à notre nginx.

## Architecture
    navigateur ─https:443─▶ Caddy ─▶ 127.0.0.1:8080 ─▶ nginx ─▶ Flask
    Pomofocus ──http:80──▶ nginx : POST / → Flask ; le reste → 301 https

## Étapes (une à la fois, vérifiée avant la suivante)
1. nginx : serveur 8080 publié sur 127.0.0.1 ; certbot retiré.
2. VPS : bloc `timer.co-libri.org` dans `/etc/caddy/Caddyfile` (cf. bloc
   apnee : `tls { issuer acme { disable_http_challenge } }`, `basic_auth`,
   `reverse_proxy 127.0.0.1:8080`), `sudo systemctl reload caddy`.
3. `~/.netrc` + URL `https://` pour `timer web-sync` et `timer_csv_backup.sh`.
4. nginx port 80 : tout sauf `POST /` → 301 https. Les pages deviennent
   privées.

## Critères de fin
- [x] `https://timer.co-libri.org/suivi` : mot de passe demandé, certificat
      valide.
- [x] `http://…/suivi` → 301 ; POST du webhook Pomofocus toujours reçu
      (vérifié en prod le 2026-10-08).
- [x] `timer web-sync` et la sauvegarde cron passent par https + `~/.netrc`.
