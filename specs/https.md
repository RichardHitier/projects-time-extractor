# SPEC — https
Date : 2026-10-08
Statut : en cours (A1 fait, A2 après le premier certificat)

Prérequis du mot de passe nginx (`specs/basic-auth.md`) : sans HTTPS, le mot
de passe circulerait en clair.

## Objectif (une phrase)
`timer.co-libri.org` servi en HTTPS (Let's Encrypt), HTTP redirigé, sans
couper le webhook Pomofocus.

## Critères de fin (3 max, observables)
- [ ] `https://timer.co-libri.org/suivi` répond, certificat valide ;
      `http://…/suivi` → 301 vers https.
- [ ] Le POST du webhook Pomofocus en HTTP est toujours reçu (pas de 301).
- [ ] Renouvellement automatique (service `certbot`, toutes les 12 h).

## Découpage
- **A1** (sans risque) : nginx sert `/.well-known/acme-challenge/` depuis
  `./certbot/www` ; service `certbot` dans le compose.
- **Amorçage** (VPS, à la main, une fois) — ci-dessous.
- **A2** (seulement après l'amorçage) : serveur 443, redirection 80 → 443,
  URL `https://` dans `config.yml` et `timer_csv_backup.sh`. Pousser A2 sans
  certificat empêche nginx de démarrer : prod coupée, webhook compris.

## Amorçage du premier certificat (VPS)
Après le déploiement de A1 :

    cd /home/debian/timer
    docker compose run --rm --entrypoint certbot certbot certonly \
        --webroot -w /var/www/certbot -d timer.co-libri.org \
        --email <ton-email> --agree-tos --no-eff-email
    ls certbot/conf/live/timer.co-libri.org/   # fullchain.pem, privkey.pem

Puis pousser A2.
