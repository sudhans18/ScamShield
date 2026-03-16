def first_or_none(value):
    if isinstance(value, list) and len(value) > 0:
        return value[0]
    return None
