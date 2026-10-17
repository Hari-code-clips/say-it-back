"""Store factory: SIB_STORE=local (JSON files) or firestore."""

from __future__ import annotations

from sayitback.settings import Settings
from sayitback.store.base import Store
from sayitback.store.local import LocalStore


def make_store(settings: Settings) -> Store:
    if settings.store == "firestore":
        from sayitback.store.firestore_store import FirestoreStore

        store = FirestoreStore.from_env()
        store.retention_days = settings.retention_days  # retention.py
        return store
    return LocalStore(settings.data_dir, settings.retention_days)


__all__ = ["LocalStore", "Store", "make_store"]
