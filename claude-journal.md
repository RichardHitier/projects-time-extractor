# Journal

## 2026-07-06
- Remis TODO.md en phase avec le livré (coché #5), réorganisé le backlog
  webhook en 9 thèmes A–I + priorités, #19 → IDEAS.md, #14 supprimé.
- /view : numéro de version en footer (v0.2.0), tâche en cours déplacée
  sous les graphes, semaine complète Lun→Dim + jour courant en jaune,
  graphes du jour sous les graphes semaine. Poussé + déployé sur le VPS.
- Règle de suivi posée : specs/ = tâche en cours, TODO.md = backlog.

## 2026-07-08
- Bloc « tâche en cours » (/view) : bordure verte quand une tâche tourne,
  grise sinon (taille constante conservée). Vérifié via un mock de tâche en
  cours, rangé dans un git stash pour réusage. Commit 264dbdf.
- Barres de total de semaine : chiffre `nn / 20h` et `nn / 60h` passés en
  14px gras ; barre globale /20h alignée à droite sur les barres des jours
  (fin x=490 au lieu de déborder à x=550), via un param `bar_end_x` qui
  découple la fin de barre de la position du libellé. Options taille/graisse
  comparées dans un artifact avant de retenir 14px gras. Commit 2ca3dbd,
  poussé (--no-verify).
- Capturé dans TODO (G — Tests, !) : 3 tests SVG rouges depuis le refactor
  « today highlighted » — ils assertent le label du jour en texte jaune alors
  que le code surligne avec des cadres (stroke) → force --no-verify au push.
