
#!/usr/bin/env python3
"""
Script pour extraire les commits de merge d'un dépôt Git
avec leur message et date/heure
"""

import subprocess
import sys
from datetime import datetime

def get_merge_commits(repo_path="."):
    """
    Extrait tous les commits de merge d'un dépôt Git

    Args:
        repo_path: Chemin vers le dépôt Git (par défaut: répertoire courant)

    Returns:
        Liste de dictionnaires contenant les informations des merges
    """
    try:
        # Commande git pour obtenir les commits de merge
        # --merges: ne montre que les commits de merge
        # --pretty=format: format personnalisé
        # %H: hash du commit
        # %ai: date au format ISO 8601
        # %s: sujet du commit (première ligne du message)
        # %b: corps du message
        cmd = [
            'git',
            '-C', repo_path,
            'log',
            '--merges',
            '--pretty=format:%H|%ai|%s|%b',
            '--date=iso'
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('|', 3)
            if len(parts) >= 3:
                commit_hash = parts[0]
                date_str = parts[1]
                message = parts[2]
                body = parts[3] if len(parts) > 3 else ""

                # Combiner le sujet et le corps du message
                full_message = message
                if body.strip():
                    full_message += "\n" + body.strip()

                commits.append({
                    'hash': commit_hash,
                    'date': date_str,
                    'message': full_message.strip()
                })

        return commits

    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de git: {e}", file=sys.stderr)
        print(f"Sortie d'erreur: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Erreur: git n'est pas installé ou non trouvé dans le PATH", file=sys.stderr)
        sys.exit(1)

def display_merge_commits(commits):
    """Affiche les commits de merge de manière formatée"""
    if not commits:
        print("Aucun commit de merge trouvé.")
        return

    print(f"{'='*80}")
    print(f"Nombre total de commits de merge: {len(commits)}")
    print(f"{'='*80}\n")

    for i, commit in enumerate(commits, 1):
        print(f"Merge #{i}")
        print(f"Date/Heure: {commit['date']}")
        print(f"Message: {commit['message']}")
        print(f"Hash: {commit['hash']}")
        print(f"{'-'*80}\n")

def export_to_csv(commits, filename="merge_commits.csv"):
    """Exporte les commits de merge vers un fichier CSV"""
    import csv

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'message', 'hash'])
            writer.writeheader()
            writer.writerows(commits)
        print(f"✓ Données exportées vers {filename}")
    except Exception as e:
        print(f"Erreur lors de l'export CSV: {e}", file=sys.stderr)

def main():
    """Fonction principale"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extrait les commits de merge d\'un dépôt Git'
    )
    parser.add_argument(
        '--repo',
        default='.',
        help='Chemin vers le dépôt Git (défaut: répertoire courant)'
    )
    parser.add_argument(
        '--csv',
        metavar='FICHIER',
        help='Exporter les résultats vers un fichier CSV'
    )

    args = parser.parse_args()

    print(f"Extraction des commits de merge depuis: {args.repo}")
    commits = get_merge_commits(args.repo)

    display_merge_commits(commits)

    if args.csv:
        export_to_csv(commits, args.csv)

if __name__ == "__main__":
    main()
