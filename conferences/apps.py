from django.apps import AppConfig


class ConferencesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'conferences'

    def ready(self):
        # Enforce single startup execution to prevent auto-reloader from running the thread twice
        import os
        if os.environ.get('RUN_MAIN') == 'true':
            self.start_scheduler()

    def start_scheduler(self):
        import threading
        import time
        from datetime import datetime, timedelta
        from django.core.management import call_command

        def scheduler_loop():
            # Wait for DB migrations to settle on server start
            time.sleep(5)
            print("[Scheduler] Background scraper thread started.")

            # Run initial scrape if DB is completely empty
            from conferences.models import Conference
            try:
                if Conference.objects.count() == 0:
                    print("[Scheduler] Empty database detected. Running initial scrape cycle...")
                    call_command('run_scraper')
            except Exception as e:
                print(f"[Scheduler] Startup scrape failed: {e}")

            while True:
                now = datetime.now()
                next_run = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                delay_seconds = (next_run - now).total_seconds()
                print(f"[Scheduler] Next scheduled scrape at midnight: {next_run} (in {delay_seconds:.1f} seconds)")

                while datetime.now() < next_run:
                    time.sleep(30)

                print("[Scheduler] Midnight reached! Starting scheduled scrape cycle...")
                try:
                    call_command('run_scraper')
                except Exception as e:
                    print(f"[Scheduler] Midnight scrape cycle failed: {e}")
                    time.sleep(60)

        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()
