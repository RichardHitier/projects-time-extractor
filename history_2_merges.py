
#!/usr/bin/env python3
"""
Script pour extraire les commits de merge d'un dépôt Git
avec leur message et date/heure
"""

import subprocess
import sys
from datetime import datetime

def get_initial_commit(repo_path="."):
    """
    Récupère le premier commit (init) du dépôt
    
    Args:
        repo_path: Chemin vers le dépôt Git
    
    Returns:
        Dictionnaire contenant les informations du commit initial
    """
    try:
        cmd = [
            'git',
            '-C', repo_path,
            'log',
            '--reverse',
            '--pretty=format:%H|%ai|%s|%b',
            '--max-count=1'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        line = result.stdout.strip()
        if not line:
            return None
            
        parts = line.split('|', 3)
        if len(parts) >= 3:
            commit_hash = parts[0]
            date_str = parts[1]
            message = parts[2]
            body = parts[3] if len(parts) > 3 else ""
            
            full_message = message
            if body.strip():
                full_message += "\n" + body.strip()
            
            return {
                'hash': commit_hash,
                'date': date_str,
                'message': full_message.strip(),
                'type': 'init'
            }
        
        return None
        
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la récupération du commit initial: {e}", file=sys.stderr)
        return None

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
            '--date=iso',
            '--reverse'  # Du plus ancien au plus récent
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
                    'message': full_message.strip(),
                    'type': 'merge'
                })
        
        return commits
        
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de git: {e}", file=sys.stderr)
        print(f"Sortie d'erreur: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Erreur: git n'est pas installé ou non trouvé dans le PATH", file=sys.stderr)
        sys.exit(1)

def calculate_time_differences(commits):
    """
    Calcule le temps écoulé entre chaque commit
    
    Args:
        commits: Liste de commits avec leur date
    
    Returns:
        Liste de commits enrichie avec les durées
    """
    from dateutil import parser
    
    enriched_commits = []
    
    for i, commit in enumerate(commits):
        commit_copy = commit.copy()
        
        if i == 0:
            # Premier commit (init ou premier merge)
            commit_copy['time_since_previous'] = None
            commit_copy['time_since_previous_str'] = "N/A (premier commit)"
        else:
            # Calculer la différence avec le commit précédent
            current_date = parser.parse(commit['date'])
            previous_date = parser.parse(commits[i-1]['date'])
            
            time_diff = current_date - previous_date
            commit_copy['time_since_previous'] = time_diff
            commit_copy['time_since_previous_str'] = format_timedelta(time_diff)
        
        enriched_commits.append(commit_copy)
    
    return enriched_commits

def format_timedelta(td):
    """
    Formate un timedelta de manière lisible
    
    Args:
        td: objet timedelta
    
    Returns:
        Chaîne formatée (ex: "2 jours, 3 heures, 45 minutes")
    """
    total_seconds = int(td.total_seconds())
    
    days = total_seconds // 86400
    remaining = total_seconds % 86400
    hours = remaining // 3600
    remaining = remaining % 3600
    minutes = remaining // 60
    seconds = remaining % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} jour{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if seconds > 0 and not parts:  # Afficher les secondes seulement si < 1 minute
        parts.append(f"{seconds} seconde{'s' if seconds > 1 else ''}")
    
    return ", ".join(parts) if parts else "0 seconde"

def display_merge_commits(commits):
    """Affiche les commits de merge de manière formatée"""
    if not commits:
        print("Aucun commit trouvé.")
        return
    
    # Compter les merges (exclure le commit init)
    merge_count = sum(1 for c in commits if c.get('type') == 'merge')
    
    print(f"{'='*80}")
    print(f"Nombre total de commits de merge: {merge_count}")
    print(f"{'='*80}\n")
    
    merge_number = 0
    for i, commit in enumerate(commits):
        if commit.get('type') == 'init':
            print(f"📍 COMMIT INITIAL")
            print(f"Date/Heure: {commit['date']}")
            print(f"Message: {commit['message']}")
            print(f"Hash: {commit['hash']}")
            print(f"{'-'*80}\n")
        else:
            merge_number += 1
            print(f"🔀 Merge #{merge_number}")
            print(f"Date/Heure: {commit['date']}")
            print(f"Message: {commit['message']}")
            print(f"Hash: {commit['hash']}")
            print(f"⏱️  Temps depuis le précédent: {commit['time_since_previous_str']}")
            print(f"{'-'*80}\n")

def export_to_csv(commits, filename="merge_commits.csv"):
    """Exporte les commits de merge vers un fichier CSV"""
    import csv
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'type', 'date', 'message', 'hash', 'time_since_previous_str'
            ])
            writer.writeheader()
            
            for commit in commits:
                row = {
                    'type': commit.get('type', 'merge'),
                    'date': commit['date'],
                    'message': commit['message'],
                    'hash': commit['hash'],
                    'time_since_previous_str': commit.get('time_since_previous_str', 'N/A')
                }
                writer.writerow(row)
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
    
    print(f"Extraction des commits depuis: {args.repo}\n")
    
    # Récupérer le commit initial
    initial_commit = get_initial_commit(args.repo)
    
    # Récupérer les commits de merge
    merge_commits = get_merge_commits(args.repo)
    
    # Combiner tous les commits
    all_commits = []
    if initial_commit:
        all_commits.append(initial_commit)
    all_commits.extend(merge_commits)
    
    # Calculer les temps écoulés
    all_commits = calculate_time_differences(all_commits)
    
    # Afficher les résultats
    display_merge_commits(all_commits)
    
    # Export CSV si demandé
    if args.csv:
        export_to_csv(all_commits, args.csv)

if __name__ == "__main__":
    main()
