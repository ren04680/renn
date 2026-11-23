"""Availability tools live in `doctors.py` (they share the slot query); re-exported here so the
module layout matches the design document."""
from backend.tools.doctors import find_joint_slots, get_availability  # noqa: F401
