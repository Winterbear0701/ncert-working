"""
Django management command to clean up expired chat cache entries
Run this daily via cron or task scheduler:
    python manage.py cleanup_cache
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from students.models import ChatCache


class Command(BaseCommand):
    help = 'Delete ChatCache entries older than 10 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find expired entries
        now = timezone.now()
        expired_entries = ChatCache.objects.filter(expires_at__lt=now)
        count = expired_entries.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No expired cache entries found'))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'🔍 DRY RUN: Would delete {count} expired cache entries'))
            for entry in expired_entries[:10]:  # Show first 10
                self.stdout.write(f"  - {entry.question[:50]}... (expired {entry.expires_at})")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
        else:
            # Delete expired entries
            deleted_count, _ = expired_entries.delete()
            self.stdout.write(
                self.style.SUCCESS(f'🗑️  Deleted {deleted_count} expired cache entries')
            )
        
        # Show statistics
        remaining = ChatCache.objects.count()
        self.stdout.write(f'📊 Remaining cache entries: {remaining}')
