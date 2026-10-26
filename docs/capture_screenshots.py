"""Reproduce README screenshots with synthetic shapes and a temporary database.

Run from the repository root: .venv/Scripts/python docs/capture_screenshots.py
No Home Assistant connection, models, cameras, or personal data are used.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

import cv2
import numpy as np
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sface_yunet"))
from review_store import ReviewStore
from face_manager import FaceManager
from web_ui import handler_for


def silhouette(color):
    canvas = np.full((300, 300, 3), (240, 236, 229), np.uint8)
    cv2.circle(canvas, (150, 106), 52, color, -1)
    cv2.ellipse(canvas, (150, 285), (100, 90), 0, 180, 360, color, -1)
    return cv2.imencode('.jpg', canvas)[1].tobytes()


images = ROOT / "docs" / "images"
images.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    trained = base / "trained"
    trained.mkdir()
    store = ReviewStore(base)
    colors = [(160, 100, 45), (98, 136, 80), (114, 80, 145)]
    for index, color in enumerate(colors):
        vector = np.eye(128, dtype=np.float32)[index]
        jpeg = silhouette(color)
        group = store.observe(vector, jpeg, 'Demo front door')
        store.db.execute('UPDATE photos SET added=0 WHERE group_id=?', (group,))
        store.db.commit()
        store.observe(vector, jpeg, 'Demo front door')
    person = store.ensure_person('Alex')
    store.add_photo(person, silhouette(colors[0]), np.eye(128, dtype=np.float32)[3])
    person = store.ensure_person('Sam')
    store.add_photo(person, silhouette(colors[1]), np.eye(128, dtype=np.float32)[4])
    manager = FaceManager(store, threading.RLock(), lambda: [], trained,
                          lambda image: (jpeg, vector), lambda: None,
                          lambda *args: {'success': True, 'faces': []})
    manager.available_cameras = lambda: [{'entity': 'camera.demo_front_door', 'name': 'Demo front door'}]
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(manager))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width': 1200, 'height': 820}, device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            expect(page.locator('#groups .face-card')).to_have_count(3)
            page.screenshot(path=str(images / 'review-inbox.png'), full_page=True)
            page.locator('#groups .face-card button').first.click()
            page.get_by_role('checkbox').first.check()
            page.get_by_label('New person name').fill('Taylor')
            page.screenshot(path=str(images / 'name-faces.png'), full_page=True)
            page.get_by_role('button', name='Assign selected photos').click()
            expect(page.locator('#editor')).not_to_be_visible()
            expect(page.locator('#toast')).not_to_be_visible()
            page.locator('[data-tab="people"]').click()
            expect(page.locator('#people .face-card')).to_have_count(3)
            page.screenshot(path=str(images / 'people.png'), full_page=True)
            page.locator('[data-tab="cameras"]').click()
            page.get_by_role('button', name='Add Home Assistant camera').click()
            page.get_by_label('Camera label').fill('Demo front door')
            page.get_by_label('Scan schedule').select_option('60')
            page.screenshot(path=str(images / 'camera-setup.png'), full_page=True)
            page.get_by_role('button', name='Cancel', exact=True).click()
            page.locator('[data-tab="review"]').click()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(images / 'mobile.png'), full_page=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        store.close()
print('Captured five screenshots using synthetic demo data only.')
