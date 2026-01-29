#!/usr/bin/env python3
"""
Sync Chat Members Script

Synchronizes members from a Telegram group to the chat_members database table.
Uses Telethon (MTProto) to fetch all group members since Bot API cannot enumerate members.

Usage:
    python scripts/sync_chat_members.py              # Run once
    python scripts/sync_chat_members.py --daemon     # Run continuously every N hours
    python scripts/sync_chat_members.py --dry-run    # Show changes without applying

Environment variables required:
    TELETHON_API_ID      - Telegram API ID (from https://my.telegram.org)
    TELETHON_API_HASH    - Telegram API Hash
    SYNC_CHAT_ID         - Telegram group/chat ID to sync from
    SYNC_INTERVAL_HOURS  - Interval between syncs in daemon mode (default: 24)

First run will prompt for phone number authentication via Telethon.
"""

import asyncio
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from telethon import TelegramClient
from telethon.tl.types import ChannelParticipantsRecent, ChannelParticipantsSearch
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError

from src.common.constants.telegram import TELEGRAM_TOKEN
from src.common.constants.sync import (
    TELETHON_API_ID,
    TELETHON_API_HASH,
    SYNC_CHAT_ID,
    SYNC_INTERVAL_HOURS,
    TELETHON_SESSION_NAME,
    SYNC_AUTO_NOTE
)
from src.common.invites import (
    get_all_pre_invited_telegram_ids,
    bulk_add_pre_invited_users,
    bulk_remove_pre_invited_users
)
from src.common.telegram_user import get_all_admin_ids

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def notify_admins(message: str):
    """Send notification message to all bot admins."""
    try:
        admin_ids = get_all_admin_ids()
        if not admin_ids:
            logger.warning("No admins found to notify")
            return
        
        for admin_id in admin_ids:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(
                    url,
                    json={
                        "chat_id": admin_id,
                        "text": f"🔔 *Chat Members Sync Alert*\n\n{message}",
                        "parse_mode": "Markdown"
                    },
                    timeout=5
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to get admin list: {e}")


def validate_config() -> bool:
    """Validate that all required configuration is present."""
    errors = []
    
    if not TELETHON_API_ID or TELETHON_API_ID == 0:
        errors.append("TELETHON_API_ID is not set")
    
    if not TELETHON_API_HASH:
        errors.append("TELETHON_API_HASH is not set")
    
    if not SYNC_CHAT_ID or SYNC_CHAT_ID == 0:
        errors.append("SYNC_CHAT_ID is not set")
    
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\nPlease set the required environment variables.")
        logger.error("Get API credentials from https://my.telegram.org")
        return False
    
    return True


async def get_group_members(client: TelegramClient, chat_id: int) -> tuple:
    """
    Fetch all members from a Telegram group/channel.
    
    Args:
        client: Authenticated Telethon client.
        chat_id: Telegram chat/channel ID.
        
    Returns:
        Tuple of (set of user IDs, dict mapping user ID to user info).
    """
    members = set()
    user_info = {}
    
    try:
        # Get the entity (group/channel)
        entity = await client.get_entity(chat_id)
        logger.info(f"Fetching members from: {getattr(entity, 'title', chat_id)}")
        
        # Iterate through all participants
        async for participant in client.iter_participants(entity):
            if not participant.bot:  # Skip bots
                members.add(participant.id)
                # Store user info for notifications
                first_name = participant.first_name or ""
                last_name = participant.last_name or ""
                username = participant.username or ""
                user_info[participant.id] = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "full_name": f"{first_name} {last_name}".strip()
                }
        
        logger.info(f"Found {len(members)} members (excluding bots)")
        
    except ChannelPrivateError:
        logger.error(f"Cannot access chat {chat_id} - it's private or you're not a member")
        raise
    except ChatAdminRequiredError:
        logger.error(f"Admin rights required to fetch members from chat {chat_id}")
        raise
    except Exception as e:
        logger.error(f"Error fetching members: {e}")
        raise
    
    return members, user_info


async def sync_members(client: TelegramClient, dry_run: bool = False) -> dict:
    """
    Synchronize Telegram group members with chat_members table.
    
    Args:
        client: Authenticated Telethon client.
        dry_run: If True, only show what would be done without making changes.
        
    Returns:
        Dict with sync statistics: added, removed, unchanged counts.
    """
    stats = {
        "group_members": 0,
        "db_members_before": 0,
        "added": 0,
        "removed": 0,
        "unchanged": 0
    }
    
    # Fetch current group members
    group_members, user_info = await get_group_members(client, SYNC_CHAT_ID)
    stats["group_members"] = len(group_members)
    
    # Get current database members
    db_members = get_all_pre_invited_telegram_ids()
    stats["db_members_before"] = len(db_members)
    
    # Calculate differences
    to_add = group_members - db_members
    to_remove = db_members - group_members
    stats["unchanged"] = len(group_members & db_members)
    
    logger.info(f"Sync analysis:")
    logger.info(f"  - Group members: {stats['group_members']}")
    logger.info(f"  - DB members: {stats['db_members_before']}")
    logger.info(f"  - To add: {len(to_add)}")
    logger.info(f"  - To remove: {len(to_remove)}")
    logger.info(f"  - Unchanged: {stats['unchanged']}")
    
    if dry_run:
        logger.info("DRY RUN - no changes will be made")
        if to_add:
            logger.info(f"Would add users: {sorted(to_add)[:10]}{'...' if len(to_add) > 10 else ''}")
        if to_remove:
            logger.info(f"Would remove users: {sorted(to_remove)[:10]}{'...' if len(to_remove) > 10 else ''}")
        stats["added"] = len(to_add)
        stats["removed"] = len(to_remove)
        return stats
    
    # Apply changes
    notification_parts = []
    
    if to_add:
        added = bulk_add_pre_invited_users(list(to_add), notes=SYNC_AUTO_NOTE)
        stats["added"] = added
        logger.info(f"Added {added} new members to chat_members")
        
        # Build notification for added users
        if added > 0:
            added_list = []
            for user_id in sorted(to_add)[:20]:  # Limit to first 20
                info = user_info.get(user_id, {})
                name = info.get("full_name", "")
                username = info.get("username", "")
                if name:
                    user_str = f"• {name}"
                    if username:
                        user_str += f" (@{username})"
                else:
                    user_str = f"• ID: {user_id}"
                added_list.append(user_str)
            
            more_text = f" (+{added - 20} more)" if added > 20 else ""
            notification_parts.append(f"✅ *Added {added} user(s)*{more_text}\n" + "\n".join(added_list))
    
    if to_remove:
        removed = bulk_remove_pre_invited_users(list(to_remove))
        stats["removed"] = removed
        logger.info(f"Removed {removed} members from chat_members")
        
        # Build notification for removed users
        if removed > 0:
            removed_list = []
            for user_id in sorted(to_remove)[:20]:  # Limit to first 20
                removed_list.append(f"• ID: {user_id}")
            
            more_text = f" (+{removed - 20} more)" if removed > 20 else ""
            notification_parts.append(f"❌ *Removed {removed} user(s)*{more_text}\n" + "\n".join(removed_list))
    
    # Notify admins if there were changes
    if notification_parts:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        notification = f"📊 Sync completed at {timestamp}\n\n" + "\n\n".join(notification_parts)
        notify_admins(notification)
    
    return stats


async def run_sync(dry_run: bool = False) -> dict:
    """
    Run a single sync operation.
    
    Args:
        dry_run: If True, only show what would be done.
        
    Returns:
        Sync statistics dict.
    """
    session_path = PROJECT_ROOT / TELETHON_SESSION_NAME
    
    async with TelegramClient(str(session_path), TELETHON_API_ID, TELETHON_API_HASH) as client:
        # Ensure we're authenticated
        if not await client.is_user_authorized():
            logger.info("First run - authentication required")
            logger.info("You will be prompted to enter your phone number and verification code")
            await client.start()
        
        return await sync_members(client, dry_run)


async def daemon_loop(dry_run: bool = False):
    """
    Run sync continuously at specified intervals.
    
    Args:
        dry_run: If True, only show what would be done.
    """
    logger.info(f"Starting daemon mode - syncing every {SYNC_INTERVAL_HOURS} hour(s)")
    
    while True:
        try:
            logger.info(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            stats = await run_sync(dry_run)
            logger.info(f"Sync completed: added={stats['added']}, removed={stats['removed']}")
        except Exception as e:
            error_msg = f"❌ *Sync failed* at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nError: `{str(e)}`"
            logger.error(f"Sync failed: {e}")
            notify_admins(error_msg)
        
        # Wait for next sync
        next_sync = datetime.now().timestamp() + (SYNC_INTERVAL_HOURS * 3600)
        next_sync_str = datetime.fromtimestamp(next_sync).strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Next sync scheduled at {next_sync_str}")
        
        await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync Telegram group members to chat_members database table"
    )
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help=f"Run continuously, syncing every {SYNC_INTERVAL_HOURS} hours"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate configuration
    if not validate_config():
        sys.exit(1)
    
    logger.info("Chat Members Sync Script")
    logger.info(f"Target chat ID: {SYNC_CHAT_ID}")
    
    try:
        if args.daemon:
            asyncio.run(daemon_loop(args.dry_run))
        else:
            stats = asyncio.run(run_sync(args.dry_run))
            logger.info("Sync completed successfully")
            logger.info(f"Final stats: {stats}")
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
