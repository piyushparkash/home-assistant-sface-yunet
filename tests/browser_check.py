"""Browser checks with synthetic silhouettes only; no private images or cameras."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

import cv2
import numpy as np
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sface_yunet'))
from review_store import ReviewStore
from face_manager import FaceManager
from web_ui import handler_for


with tempfile.TemporaryDirectory() as directory:
    base=Path(directory)
    trained=base/'trained'
    trained.mkdir()
    canvas=np.full((240,240,3),(228,213,194),np.uint8)
    cv2.circle(canvas,(120,90),44,(140,95,54),-1)
    cv2.ellipse(canvas,(120,210),(80,65),0,180,360,(140,95,54),-1)
    jpeg=cv2.imencode('.jpg',canvas)[1].tobytes()
    vec=np.zeros(128,np.float32)
    vec[0]=1
    store=ReviewStore(base)
    known=store.ensure_person('Test Person')
    store.add_photo(known,jpeg,vec)
    group=store.observe(vec,jpeg,'Test camera')
    store.db.execute('UPDATE photos SET added=0 WHERE group_id=?',(group,))
    store.db.commit()
    store.observe(vec,jpeg,'Test camera')
    manager=FaceManager(store,threading.RLock(),lambda:[],trained,
                        lambda image:(jpeg,vec),lambda:None,lambda *args:{'success':True,'faces':[]})
    manager.available_cameras=lambda:[{'entity':'camera.synthetic','name':'Synthetic camera'}]
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(manager))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch()
            page=browser.new_page(viewport={'width':1280,'height':960})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
            expect(page.get_by_role('heading',name='Who is this?')).to_be_visible()
            expect(page.locator('#groups .face-card')).to_have_count(1)
            if len(sys.argv)>1:
                page.screenshot(path=sys.argv[1],full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            if len(sys.argv)>2:
                page.screenshot(path=sys.argv[2],full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#groups .face-card button').click()
            page.get_by_role('checkbox').first.check()
            page.get_by_label('New person name').fill('Test Visitor')
            page.get_by_role('button',name='Assign selected photos').click()
            expect(page.locator('#editor')).not_to_be_visible()
            assert len(store.embeddings())==2
            assert len(store.groups()[0]['photos'])==1
            page.locator('[data-tab="people"]').click()
            page.locator('#people .face-card button').filter(has_text='Test Visitor').click()
            page.get_by_label('Display name').fill('Renamed Visitor')
            page.get_by_role('button',name='Save name').click()
            expect(page.locator('#people')).to_contain_text('Renamed Visitor')
            assert store.names()['test_visitor']=='Renamed Visitor'
            page.get_by_role('button',name='Add face photos',exact=True).click()
            page.get_by_label('Assign to').select_option('test_visitor')
            page.get_by_label('Face photo').set_input_files({'name':'synthetic.jpg','mimeType':'image/jpeg','buffer':jpeg})
            page.get_by_role('button',name='Add photos',exact=True).click()
            expect(page.locator('#editor')).not_to_be_visible()
            assert len(store.known_photos('test_visitor'))==2
            page.locator('[data-tab="cameras"]').click()
            page.get_by_role('button',name='Add Home Assistant camera').click()
            page.get_by_label('Camera label').fill('Test camera')
            page.get_by_role('button',name='Save camera').click()
            expect(page.locator('#cameras')).to_contain_text('Test camera')
            assert manager.cameras()[0]['entity']=='camera.synthetic'
            assert not errors, errors
            browser.close()
        print('Browser checks passed: desktop, mobile, selected assignment, rename, upload, camera setup')
    finally:
        server.shutdown()
        server.server_close()
        store.close()
