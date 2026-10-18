"""Diagnostics intentionally exclude enrollment keys and connection challenges."""
from dataclasses import asdict
async def async_get_config_entry_diagnostics(hass, entry):
    coordinator=entry.runtime_data
    return {'status':asdict(coordinator.data) if coordinator.data else None,
            'settings':asdict(coordinator.blind.settings)}
