import discord, time

from discord import app_commands
from collections import defaultdict, deque


MAX_CALLS_PER_MINUTE = 10

LOCK_DURATION = 180  # 3 minutes

command_usage = defaultdict(lambda: deque(maxlen=11))

locked_users = []

lock_expiry = {}


class RateLimitExceeded(app_commands.CheckFailure):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def rate_limit_check():    
    def predicate(interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        now = time.time()

        if user_id in lock_expiry and now > lock_expiry[user_id]:
            locked_users.remove(user_id)
            del lock_expiry[user_id]

        if user_id in locked_users:
            remaining = int(lock_expiry[user_id] - now)
            minutes, seconds = divmod(remaining, 60)
            formatted = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            raise RateLimitExceeded(
                f"You're currently locked out due to too many commands. Try again in {formatted}."
            )

        usage = command_usage[user_id]
        usage.append(now)

        while usage and now - usage[0] > 3600:
            usage.popleft()

        calls_last_minute = [t for t in usage if now - t <= 60]

        if len(calls_last_minute) > MAX_CALLS_PER_MINUTE:
            locked_users.append(user_id)
            lock_expiry[user_id] = now + LOCK_DURATION
            raise RateLimitExceeded(
                f"Too many commands — you've been locked out for {LOCK_DURATION // 60} minutes."
            )

        return True

    return app_commands.check(predicate)
