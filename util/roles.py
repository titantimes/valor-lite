import discord, logging
from core.config import config

def _has_role(user_roles: list[discord.Role], allowed_roles) -> bool:
    if config.TESTING:
        return True

    user_role_ids = {role.id for role in user_roles}
    return not user_role_ids.isdisjoint(allowed_roles)

def is_ANO_member(user_roles: list[discord.Role]) -> bool:
    return _has_role(user_roles, config.ANO_MEMBER_ROLES)

def is_ANO_military_member(user_roles: list[discord.Role]) -> bool:
    return _has_role(user_roles, config.ANO_MILITARY_ROLES)

def is_ANO_high_rank(user_roles: list[discord.Role]) -> bool:
    return _has_role(user_roles, config.ANO_HIGH_RANK_ROLES)

def is_ANO_titan_rank(user_roles: list[discord.Role]) -> bool:
    return _has_role(user_roles, config.ANO_TITAN_ROLES)

def is_ANO_chief(user_roles: list[discord.Role]) -> bool:
    return _has_role(user_roles, config.ANO_CHIEF_ROLES)
