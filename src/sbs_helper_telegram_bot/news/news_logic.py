"""
News Module Logic

Business logic, database operations, broadcasting, and search functionality.
"""

import asyncio
import time
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from telegram import Bot
from telegram.error import TelegramError

import src.common.database as database
from src.common import bot_settings
from . import settings
from . import messages

logger = logging.getLogger(__name__)


# ===== SETTINGS HELPERS =====


def get_news_expiry_days() -> int:
    """
    Get the news expiry days setting.
    
    Returns:
        Number of days after which news is considered archived
    """
    value = bot_settings.get_setting(settings.SETTING_NEWS_EXPIRY_DAYS)
    try:
        return int(value) if value else settings.DEFAULT_NEWS_EXPIRY_DAYS
    except (ValueError, TypeError):
        return settings.DEFAULT_NEWS_EXPIRY_DAYS


def set_news_expiry_days(days: int, updated_by: Optional[int] = None) -> bool:
    """
    Set the news expiry days setting.
    
    Args:
        days: Number of days
        updated_by: Admin user ID
        
    Returns:
        True if successful
    """
    return bot_settings.set_setting(settings.SETTING_NEWS_EXPIRY_DAYS, str(days), updated_by)


# ===== CATEGORIES =====


def get_active_categories() -> List[Dict[str, Any]]:
    """
    Get all active news categories.
    
    Returns:
        List of category dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT id, name, emoji, description, display_order
                    FROM news_categories
                    WHERE active = 1
                    ORDER BY display_order ASC, id ASC
                """)
                return cursor.fetchall() or []
    except Exception as e:
        logger.error("Error getting news categories: %s", e)
        return []


def get_all_categories() -> List[Dict[str, Any]]:
    """
    Get all categories (active and inactive) with article counts.
    
    Returns:
        List of category dicts with article_count
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT 
                        c.id, c.name, c.emoji, c.description, c.display_order, c.active,
                        COUNT(a.id) as article_count
                    FROM news_categories c
                    LEFT JOIN news_articles a ON c.id = a.category_id
                    GROUP BY c.id
                    ORDER BY c.display_order ASC, c.id ASC
                """)
                return cursor.fetchall() or []
    except Exception as e:
        logger.error("Error getting all categories: %s", e)
        return []


def get_category_by_id(category_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a category by ID.
    
    Args:
        category_id: Category ID
        
    Returns:
        Category dict or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT id, name, emoji, description, display_order, active
                    FROM news_categories
                    WHERE id = %s
                """, (category_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error("Error getting category %s: %s", category_id, e)
        return None


def create_category(name: str, emoji: str = "📰", description: str = None) -> Optional[int]:
    """
    Create a new category.
    
    Args:
        name: Category name
        emoji: Category emoji
        description: Category description
        
    Returns:
        Created category ID or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT INTO news_categories (name, emoji, description, created_timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (name, emoji, description, int(time.time())))
                conn.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error("Error creating category: %s", e)
        return None


def update_category(category_id: int, **kwargs) -> bool:
    """
    Update a category.
    
    Args:
        category_id: Category ID
        **kwargs: Fields to update (name, emoji, description, active, display_order)
        
    Returns:
        True if successful
    """
    if not kwargs:
        return True
    
    allowed_fields = {'name', 'emoji', 'description', 'active', 'display_order'}
    fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if not fields:
        return True
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                set_clause = ", ".join(f"{k} = %s" for k in fields.keys())
                values = list(fields.values())
                values.append(int(time.time()))
                values.append(category_id)
                
                cursor.execute(f"""
                    UPDATE news_categories
                    SET {set_clause}, updated_timestamp = %s
                    WHERE id = %s
                """, values)
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error updating category %s: %s", category_id, e)
        return False


def delete_category(category_id: int) -> Tuple[bool, str]:
    """
    Delete a category if it has no articles.
    
    Args:
        category_id: Category ID
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Check for articles
                cursor.execute("""
                    SELECT COUNT(*) as count FROM news_articles WHERE category_id = %s
                """, (category_id,))
                result = cursor.fetchone()
                if result and result['count'] > 0:
                    return False, "has_articles"
                
                cursor.execute("DELETE FROM news_categories WHERE id = %s", (category_id,))
                conn.commit()
                return True, ""
    except Exception as e:
        logger.error("Error deleting category %s: %s", category_id, e)
        return False, str(e)


# ===== ARTICLES =====


def create_article(
    title: str,
    content: str,
    category_id: int,
    created_by: int,
    is_silent: bool = False,
    is_mandatory: bool = False,
    image_file_id: str = None,
    attachment_file_id: str = None,
    attachment_filename: str = None
) -> Optional[int]:
    """
    Create a new news article (draft).
    
    Returns:
        Created article ID or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT INTO news_articles 
                    (title, content, category_id, created_by_userid, is_silent, is_mandatory,
                     image_file_id, attachment_file_id, attachment_filename, created_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    title, content, category_id, created_by,
                    1 if is_silent else 0,
                    1 if is_mandatory else 0,
                    image_file_id, attachment_file_id, attachment_filename,
                    int(time.time())
                ))
                conn.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error("Error creating article: %s", e)
        return None


def get_article_by_id(article_id: int) -> Optional[Dict[str, Any]]:
    """
    Get an article by ID with category info.
    
    Returns:
        Article dict or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT 
                        a.*,
                        c.name as category_name,
                        c.emoji as category_emoji
                    FROM news_articles a
                    JOIN news_categories c ON a.category_id = c.id
                    WHERE a.id = %s
                """, (article_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error("Error getting article %s: %s", article_id, e)
        return None


def get_articles_by_status(
    status: str,
    page: int = 0,
    per_page: int = settings.ITEMS_PER_PAGE
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get articles by status with pagination.
    
    Returns:
        Tuple of (articles list, total count)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get total count
                cursor.execute("""
                    SELECT COUNT(*) as count FROM news_articles WHERE status = %s
                """, (status,))
                total = cursor.fetchone()['count']
                
                # Get paginated results
                offset = page * per_page
                cursor.execute("""
                    SELECT 
                        a.id, a.title, a.status, a.is_silent, a.is_mandatory,
                        a.created_timestamp, a.published_timestamp,
                        c.emoji as category_emoji, c.name as category_name
                    FROM news_articles a
                    JOIN news_categories c ON a.category_id = c.id
                    WHERE a.status = %s
                    ORDER BY a.created_timestamp DESC
                    LIMIT %s OFFSET %s
                """, (status, per_page, offset))
                
                return cursor.fetchall() or [], total
    except Exception as e:
        logger.error("Error getting articles by status %s: %s", status, e)
        return [], 0


def get_published_news(
    page: int = 0,
    per_page: int = settings.ITEMS_PER_PAGE,
    include_expired: bool = False
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get published news articles with pagination.
    
    Args:
        page: Page number (0-indexed)
        per_page: Items per page
        include_expired: Whether to include news older than expiry days
        
    Returns:
        Tuple of (articles list, total count)
    """
    try:
        expiry_days = get_news_expiry_days()
        expiry_timestamp = int(time.time()) - (expiry_days * 24 * 60 * 60)
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Build WHERE clause
                if include_expired:
                    where_clause = "a.status = 'published' AND a.published_timestamp <= %s"
                    params = [expiry_timestamp]
                else:
                    where_clause = "a.status = 'published' AND a.published_timestamp > %s"
                    params = [expiry_timestamp]
                
                # Get total count
                cursor.execute(f"""
                    SELECT COUNT(*) as count FROM news_articles a WHERE {where_clause}
                """, params)
                total = cursor.fetchone()['count']
                
                # Get paginated results
                offset = page * per_page
                params.extend([per_page, offset])
                cursor.execute(f"""
                    SELECT 
                        a.id, a.title, a.content, a.status, a.is_mandatory,
                        a.image_file_id, a.attachment_file_id, a.attachment_filename,
                        a.published_timestamp,
                        c.emoji as category_emoji, c.name as category_name
                    FROM news_articles a
                    JOIN news_categories c ON a.category_id = c.id
                    WHERE {where_clause}
                    ORDER BY a.published_timestamp DESC
                    LIMIT %s OFFSET %s
                """, params)
                
                return cursor.fetchall() or [], total
    except Exception as e:
        logger.error("Error getting published news: %s", e)
        return [], 0


def update_article(article_id: int, **kwargs) -> bool:
    """
    Update an article.
    
    Args:
        article_id: Article ID
        **kwargs: Fields to update
        
    Returns:
        True if successful
    """
    if not kwargs:
        return True
    
    allowed_fields = {
        'title', 'content', 'category_id', 'status', 'is_silent', 'is_mandatory',
        'image_file_id', 'attachment_file_id', 'attachment_filename', 'published_timestamp'
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if not fields:
        return True
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                set_clause = ", ".join(f"{k} = %s" for k in fields.keys())
                values = list(fields.values())
                values.append(int(time.time()))
                values.append(article_id)
                
                cursor.execute(f"""
                    UPDATE news_articles
                    SET {set_clause}, updated_timestamp = %s
                    WHERE id = %s
                """, values)
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error updating article %s: %s", article_id, e)
        return False


def publish_article(article_id: int) -> bool:
    """
    Publish an article (change status to published).
    
    Returns:
        True if successful
    """
    return update_article(
        article_id,
        status=settings.STATUS_PUBLISHED,
        published_timestamp=int(time.time())
    )


def delete_article(article_id: int) -> bool:
    """
    Delete an article.
    
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("DELETE FROM news_articles WHERE id = %s", (article_id,))
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error deleting article %s: %s", article_id, e)
        return False


# ===== SEARCH =====


def search_news(
    query: str,
    page: int = 0,
    per_page: int = settings.ITEMS_PER_PAGE
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Search news by keyword in title and content.
    
    Args:
        query: Search query
        page: Page number (0-indexed)
        per_page: Items per page
        
    Returns:
        Tuple of (articles list, total count)
    """
    try:
        search_pattern = f"%{query}%"
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get total count
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM news_articles a
                    WHERE a.status = 'published'
                    AND (a.title LIKE %s OR a.content LIKE %s)
                """, (search_pattern, search_pattern))
                total = cursor.fetchone()['count']
                
                # Get paginated results
                offset = page * per_page
                cursor.execute("""
                    SELECT 
                        a.id, a.title, a.content, a.published_timestamp,
                        c.emoji as category_emoji, c.name as category_name
                    FROM news_articles a
                    JOIN news_categories c ON a.category_id = c.id
                    WHERE a.status = 'published'
                    AND (a.title LIKE %s OR a.content LIKE %s)
                    ORDER BY a.published_timestamp DESC
                    LIMIT %s OFFSET %s
                """, (search_pattern, search_pattern, per_page, offset))
                
                return cursor.fetchall() or [], total
    except Exception as e:
        logger.error("Error searching news: %s", e)
        return [], 0


# ===== REACTIONS =====


def get_article_reactions(article_id: int) -> Dict[str, int]:
    """
    Get reaction counts for an article.
    
    Returns:
        Dict with like/love/dislike counts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT reaction_type, COUNT(*) as count
                    FROM news_reactions
                    WHERE news_id = %s
                    GROUP BY reaction_type
                """, (article_id,))
                
                results = cursor.fetchall() or []
                reactions = {'like': 0, 'love': 0, 'dislike': 0}
                for row in results:
                    reactions[row['reaction_type']] = row['count']
                return reactions
    except Exception as e:
        logger.error("Error getting reactions for article %s: %s", article_id, e)
        return {'like': 0, 'love': 0, 'dislike': 0}


def get_user_reaction(article_id: int, user_id: int) -> Optional[str]:
    """
    Get user's reaction type for an article.
    
    Returns:
        Reaction type or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT reaction_type FROM news_reactions
                    WHERE news_id = %s AND user_id = %s
                """, (article_id, user_id))
                result = cursor.fetchone()
                return result['reaction_type'] if result else None
    except Exception as e:
        logger.error("Error getting user reaction: %s", e)
        return None


def set_reaction(article_id: int, user_id: int, reaction_type: str) -> bool:
    """
    Set or update user's reaction on an article.
    If the same reaction exists, removes it (toggle behavior).
    
    Returns:
        True if reaction was added, False if removed
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Check existing reaction
                cursor.execute("""
                    SELECT reaction_type FROM news_reactions
                    WHERE news_id = %s AND user_id = %s
                """, (article_id, user_id))
                existing = cursor.fetchone()
                
                if existing and existing['reaction_type'] == reaction_type:
                    # Toggle off - remove reaction
                    cursor.execute("""
                        DELETE FROM news_reactions
                        WHERE news_id = %s AND user_id = %s
                    """, (article_id, user_id))
                    conn.commit()
                    return False
                else:
                    # Add or change reaction
                    cursor.execute("""
                        INSERT INTO news_reactions (news_id, user_id, reaction_type, created_timestamp)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE reaction_type = %s, created_timestamp = %s
                    """, (article_id, user_id, reaction_type, int(time.time()), reaction_type, int(time.time())))
                    conn.commit()
                    return True
    except Exception as e:
        logger.error("Error setting reaction: %s", e)
        return False


# ===== READ TRACKING =====


def get_unread_count(user_id: int) -> int:
    """
    Get count of unread news for a user.
    
    Returns:
        Number of unread news articles
    """
    try:
        expiry_days = get_news_expiry_days()
        expiry_timestamp = int(time.time()) - (expiry_days * 24 * 60 * 60)
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get user's last read timestamp
                cursor.execute("""
                    SELECT last_read_timestamp FROM news_read_log WHERE user_id = %s
                """, (user_id,))
                result = cursor.fetchone()
                last_read = result['last_read_timestamp'] if result else 0
                
                # Count news published after last read and not expired
                cursor.execute("""
                    SELECT COUNT(*) as count FROM news_articles
                    WHERE status = 'published'
                    AND published_timestamp > %s
                    AND published_timestamp > %s
                """, (last_read, expiry_timestamp))
                
                return cursor.fetchone()['count']
    except Exception as e:
        logger.error("Error getting unread count for user %s: %s", user_id, e)
        return 0


def mark_all_as_read(user_id: int) -> bool:
    """
    Mark all news as read for a user (update last_read_timestamp).
    
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT INTO news_read_log (user_id, last_read_timestamp)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE last_read_timestamp = %s
                """, (user_id, int(time.time()), int(time.time())))
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error marking news as read for user %s: %s", user_id, e)
        return False


# ===== MANDATORY NEWS =====


def get_unacked_mandatory_news(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the oldest unacknowledged mandatory news for a user.
    
    Returns:
        Article dict or None if no unacked mandatory news
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT 
                        a.id, a.title, a.content, a.image_file_id,
                        a.attachment_file_id, a.attachment_filename,
                        a.published_timestamp,
                        c.emoji as category_emoji, c.name as category_name
                    FROM news_articles a
                    JOIN news_categories c ON a.category_id = c.id
                    LEFT JOIN news_mandatory_ack ack ON a.id = ack.news_id AND ack.user_id = %s
                    WHERE a.status = 'published'
                    AND a.is_mandatory = 1
                    AND ack.id IS NULL
                    ORDER BY a.published_timestamp ASC
                    LIMIT 1
                """, (user_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error("Error getting unacked mandatory news for user %s: %s", user_id, e)
        return None


def acknowledge_mandatory_news(news_id: int, user_id: int) -> bool:
    """
    Record user's acknowledgment of mandatory news.
    
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT IGNORE INTO news_mandatory_ack (news_id, user_id, ack_timestamp)
                    VALUES (%s, %s, %s)
                """, (news_id, user_id, int(time.time())))
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error acknowledging mandatory news: %s", e)
        return False


def has_unacked_mandatory_news(user_id: int) -> bool:
    """
    Check if user has any unacknowledged mandatory news.
    
    Returns:
        True if there is unacked mandatory news
    """
    return get_unacked_mandatory_news(user_id) is not None


# ===== BROADCASTING =====


def get_all_user_ids() -> List[int]:
    """
    Get all active user IDs for broadcasting.
    
    Returns:
        List of user IDs
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("SELECT userid FROM users")
                results = cursor.fetchall() or []
                return [row['userid'] for row in results]
    except Exception as e:
        logger.error("Error getting user IDs: %s", e)
        return []


def log_delivery(news_id: int, user_id: int, status: str, error_message: str = None) -> bool:
    """
    Log news delivery status.
    
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT INTO news_delivery_log (news_id, user_id, status, error_message, delivered_timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE status = %s, error_message = %s, delivered_timestamp = %s
                """, (
                    news_id, user_id, status, error_message, int(time.time()),
                    status, error_message, int(time.time())
                ))
                conn.commit()
                return True
    except Exception as e:
        logger.error("Error logging delivery: %s", e)
        return False


def get_delivery_stats(news_id: int) -> Dict[str, int]:
    """
    Get delivery statistics for an article.
    
    Returns:
        Dict with 'sent', 'failed', 'total' counts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM news_delivery_log
                    WHERE news_id = %s
                    GROUP BY status
                """, (news_id,))
                
                results = cursor.fetchall() or []
                stats = {'sent': 0, 'failed': 0}
                for row in results:
                    stats[row['status']] = row['count']
                stats['total'] = stats['sent'] + stats['failed']
                return stats
    except Exception as e:
        logger.error("Error getting delivery stats: %s", e)
        return {'sent': 0, 'failed': 0, 'total': 0}


def get_failed_deliveries(news_id: int) -> List[int]:
    """
    Get user IDs with failed delivery for retry.
    
    Returns:
        List of user IDs
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT user_id FROM news_delivery_log
                    WHERE news_id = %s AND status = 'failed'
                """, (news_id,))
                results = cursor.fetchall() or []
                return [row['user_id'] for row in results]
    except Exception as e:
        logger.error("Error getting failed deliveries: %s", e)
        return []


async def broadcast_news(
    bot: Bot,
    article: Dict[str, Any],
    user_ids: List[int],
    progress_callback: callable = None
) -> Dict[str, int]:
    """
    Broadcast news article to users with rate limiting.
    
    Args:
        bot: Telegram Bot instance
        article: Article dict with content, image_file_id, etc.
        user_ids: List of user IDs to send to
        progress_callback: Optional async callback(sent, failed, total) for progress updates
        
    Returns:
        Dict with 'sent' and 'failed' counts
    """
    results = {'sent': 0, 'failed': 0}
    total = len(user_ids)
    
    # Format the article text
    title = messages.escape_markdown_v2(article['title'])
    content = article['content']  # Already formatted
    category_emoji = article.get('category_emoji', '📰')
    category_name = messages.escape_markdown_v2(article.get('category_name', ''))
    
    published_ts = article.get('published_timestamp', int(time.time()))
    published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
    published_date = messages.escape_markdown_v2(published_date)
    
    # Get reactions
    reactions = get_article_reactions(article['id'])
    
    text = messages.format_news_article(
        title=title,
        content=content,
        category_emoji=category_emoji,
        category_name=category_name,
        published_date=published_date,
        reactions=reactions
    )
    
    from . import keyboards
    reaction_keyboard = keyboards.get_reaction_keyboard(article['id'], reactions)
    
    for i, user_id in enumerate(user_ids):
        try:
            if article.get('image_file_id'):
                # Send with image
                await bot.send_photo(
                    chat_id=user_id,
                    photo=article['image_file_id'],
                    caption=text,
                    parse_mode='MarkdownV2',
                    reply_markup=reaction_keyboard
                )
            else:
                # Send text only
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='MarkdownV2',
                    reply_markup=reaction_keyboard
                )
            
            # Send attachment if present
            if article.get('attachment_file_id'):
                await bot.send_document(
                    chat_id=user_id,
                    document=article['attachment_file_id'],
                    filename=article.get('attachment_filename')
                )
            
            log_delivery(article['id'], user_id, 'sent')
            results['sent'] += 1
            
        except TelegramError as e:
            logger.warning("Failed to send news to user %s: %s", user_id, e)
            log_delivery(article['id'], user_id, 'failed', str(e)[:500])
            results['failed'] += 1
        except Exception as e:
            logger.error("Unexpected error sending news to user %s: %s", user_id, e)
            log_delivery(article['id'], user_id, 'failed', str(e)[:500])
            results['failed'] += 1
        
        # Progress callback
        if progress_callback and (i + 1) % settings.BROADCAST_PROGRESS_INTERVAL == 0:
            await progress_callback(results['sent'], results['failed'], total)
        
        # Rate limiting - 0.1s delay = 10 messages/sec (safe margin)
        await asyncio.sleep(settings.BROADCAST_DELAY_SECONDS)
    
    return results


# ===== UTILITY FUNCTIONS =====


def format_timestamp(timestamp: int) -> str:
    """
    Format Unix timestamp to readable date string.
    
    Returns:
        Formatted date string
    """
    return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')


def split_message(text: str, max_len: int = settings.MAX_MESSAGE_LENGTH) -> List[str]:
    """
    Split text into chunks respecting Telegram's message limit.
    
    Args:
        text: Text to split
        max_len: Maximum length per chunk
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_len:
        return [text]
    
    chunks = []
    while len(text) > max_len:
        # Try to find a good split point (newline)
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            # No good newline, split at space
            split_at = text.rfind(' ', 0, max_len)
        if split_at == -1:
            # No space either, hard split
            split_at = max_len
        
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    
    if text:
        chunks.append(text)
    
    return chunks
