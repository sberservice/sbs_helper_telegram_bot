#!/usr/bin/env python3
"""
Add Daily Scores Script

External script to add score points to users.
Can be called from cron jobs, external systems, or admin tools.

Usage:
    python add_daily_scores.py --userid 123456789 --points 10 --reason "Daily bonus"
    python add_daily_scores.py --file users.csv --points 5 --reason "Weekly reward"
    python add_daily_scores.py --all-active --points 1 --reason "Activity bonus"

Arguments:
    --userid INT        Single user ID to award points
    --file FILE         CSV file with user IDs (one per line)
    --all-active        Award to all users active in last 7 days
    --points INT        Points to award (required)
    --reason TEXT       Reason for the points (optional)
    --source TEXT       Source identifier (default: 'external')
    --dry-run           Show what would be done without making changes
"""

import argparse
import csv
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sbs_helper_telegram_bot.gamification.gamification_logic import add_score_points
import src.common.database as database


def get_active_user_ids(days: int = 7) -> list:
    """Get user IDs active in last N days."""
    import time
    since = int(time.time()) - (days * 24 * 60 * 60)
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT DISTINCT userid FROM gamification_events
                WHERE timestamp > %s
            """, (since,))
            return [row['userid'] for row in cursor.fetchall()]


def load_user_ids_from_file(filepath: str) -> list:
    """Load user IDs from CSV file."""
    user_ids = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip().isdigit():
                user_ids.append(int(row[0].strip()))
    return user_ids


def main():
    parser = argparse.ArgumentParser(
        description='Add score points to users',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # User selection (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--userid', type=int, help='Single user ID')
    group.add_argument('--file', type=str, help='CSV file with user IDs')
    group.add_argument('--all-active', action='store_true', 
                       help='All users active in last 7 days')
    
    # Points configuration
    parser.add_argument('--points', type=int, required=True,
                        help='Points to award (can be negative)')
    parser.add_argument('--reason', type=str, default=None,
                        help='Reason for the points')
    parser.add_argument('--source', type=str, default='external',
                        help='Source identifier (default: external)')
    
    # Options
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    # Collect user IDs
    user_ids = []
    
    if args.userid:
        user_ids = [args.userid]
    elif args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        user_ids = load_user_ids_from_file(args.file)
    elif args.all_active:
        user_ids = get_active_user_ids()
    
    if not user_ids:
        print("No users found to award points to.")
        sys.exit(0)
    
    print(f"Adding {args.points} points to {len(user_ids)} user(s)")
    print(f"Source: {args.source}")
    print(f"Reason: {args.reason or '(none)'}")
    print()
    
    if args.dry_run:
        print("DRY RUN - No changes will be made")
        print()
        for uid in user_ids[:10]:
            print(f"  Would award {args.points} points to user {uid}")
        if len(user_ids) > 10:
            print(f"  ... and {len(user_ids) - 10} more users")
        sys.exit(0)
    
    # Award points
    success_count = 0
    error_count = 0
    
    for uid in user_ids:
        try:
            result = add_score_points(
                userid=uid,
                points=args.points,
                source=args.source,
                reason=args.reason
            )
            if result:
                success_count += 1
                print(f"  ✓ User {uid}: +{args.points} points")
            else:
                error_count += 1
                print(f"  ✗ User {uid}: Failed to add points")
        except Exception as e:
            error_count += 1
            print(f"  ✗ User {uid}: Error - {e}")
    
    print()
    print(f"Summary: {success_count} successful, {error_count} errors")
    
    if error_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
