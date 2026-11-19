"""Non-secret deployment configuration validation."""


def reset_guild_ids(value):
    """An empty allowlist disables resets; malformed lists never allow access."""
    if not value.strip():return frozenset()
    values=[part.strip() for part in value.split(',')]
    if any(len(part)>20 or not part.isascii() or not part.isdecimal() or not 0<int(part)<2**64 for part in values):
        raise ValueError('PORTLE_RESET_GUILD_IDS must be a comma-separated list of positive server IDs, or blank to disable resets.')
    return frozenset(int(part) for part in values)
