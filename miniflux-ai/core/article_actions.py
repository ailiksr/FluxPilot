from core.miniflux_client import get_miniflux_client

def archive_entry(entry_id: int):
    client=get_miniflux_client()
    return client.update_entries([int(entry_id)], "read")


def restore_entry(entry_id: int):
    client=get_miniflux_client()
    return client.update_entries([int(entry_id)], "unread")
