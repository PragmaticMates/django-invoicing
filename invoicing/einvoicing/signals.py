from django.dispatch import Signal


# Sent after a transmission's status changed, with ``transmission`` and ``previous_status``
transmission_status_changed = Signal()
