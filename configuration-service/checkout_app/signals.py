"""Keeps the service providers' weeks in step with the bookings (checkout_app.schedule): every save
of a ScheduleItem writes it into its provider's WeeklyAvailability (H while pending payment, X once
paid or completed), moving it frees its old time, and deleting it frees its time (back to O).

Note: QuerySet.update() doesn't send these signals; change bookings' status or times with save().
"""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import schedule
from .models import ScheduleItem


@receiver(pre_save, sender=ScheduleItem)
def remember_old_time(sender, instance: ScheduleItem, raw=False, **kwargs):
    """Where the booking was before this save, to free it if it moves."""
    instance._old_time = None
    if raw or instance.pk is None:
        return
    old = ScheduleItem.objects.filter(pk=instance.pk).values(
        'service_provider_id', 'start_time', 'end_time', 'blocked_until'
    ).first()
    instance._old_time = old


@receiver(post_save, sender=ScheduleItem)
def write_booking(sender, instance: ScheduleItem, raw=False, **kwargs):
    if raw:  # loaddata: fixtures already hold the letters
        return
    old = getattr(instance, '_old_time', None)
    if old and (old['service_provider_id'], old['start_time'], old['blocked_until']) != (
        instance.service_provider_id, instance.start_time, instance.blocked_until
    ):
        schedule.release_booking(old['service_provider_id'], old['start_time'], old['end_time'], old['blocked_until'])
    schedule.sync_booking(instance)


@receiver(post_delete, sender=ScheduleItem)
def free_booking(sender, instance: ScheduleItem, **kwargs):
    schedule.release_booking(instance.service_provider_id, instance.start_time, instance.end_time, instance.blocked_until)
