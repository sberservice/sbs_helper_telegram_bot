"""
invites.py

Invite code management utilities.

Functions:
- generate_invite_string(length=6) -> str: Generates an uppercase alphanumeric code (without 0).
- invite_exists(invite) -> bool: Checks if an invite code already exists in the database.
- generate_invite_for_user(user_id) -> str: Creates/stores a unique unused invite code for a user.
"""

import string
import random
import src.common.database as database
from src.common.constants.errorcodes import InviteStatus

def generate_invite_string(length=6)->str:
    """
        Generate a random invite code of the specified length.

        The code consists only of uppercase Latin letters (A-Z) and digits 1-9
        (digit 0 is excluded to avoid confusion with the letter O).

        Args:
            length: Length of the invite code (default: 6).

        Returns:
            Random invite string of the requested length.
    """
    return ''.join(random.choice(string.ascii_uppercase + string.digits[1:]) for _ in range(length))
def invite_exists(invite)->bool:
    """
    Check whether an invite code already exists in the database.

    Args:
        invite (str): The invite code to look up.

    Returns:
        bool: True if the invite code is already present in the `invites` table,
              False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(*) as invites_count from invites where invite=%s"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            return result["invites_count"]>0

def generate_invite_for_user(user_id):
    """
        Generates a unique 6-character invite code and assigns it to the given user.

        Keeps generating random codes until a non-existing one is found,
        then inserts it into the `invites` table with the current timestamp.

        Args:
            user_id (int): Telegram user ID to whom the invite will be issued.

        Returns:
            str: The newly created unique invite code.
    """
    while True:
        invite=generate_invite_string(6)
        if invite_exists(invite):
            pass
        else:
            break
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "INSERT INTO invites (userid,invite,issued_timestamp) VALUES (%s,%s,UNIX_TIMESTAMP())"
            val = (user_id,invite)
            cursor.execute(sql, val)
            return invite
