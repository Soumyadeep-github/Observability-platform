"""Live service entry point. Historical demo is a separate opt-in application."""
import os

def create_app(db_path=None, **options):
    if os.environ.get('OBS_MODE') == 'demo':
        from .legacy_demo import create_app as demo
        return demo(db_path)
    from .live import live_app
    return live_app(db_path, **options)
