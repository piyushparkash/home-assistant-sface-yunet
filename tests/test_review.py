import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sface_yunet'))
from review_store import ReviewStore
from face_manager import FaceManager,legacy_id
from ha_bridge import HomeAssistantBridge
from web_ui import handler_for


def vector(n=0):
    result=np.zeros(128,dtype=np.float32)
    result[n]=1
    return result


JPEG=cv2.imencode('.jpg',np.full((96,96,3),128,np.uint8))[1].tobytes()


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.base=Path(self.directory.name)
        self.store=ReviewStore(self.base)
        self.lock=threading.RLock()
        self.trained=self.base/'trained'
        (self.trained/'person_one').mkdir(parents=True)
        (self.trained/'person_one'/'photo.jpg').write_bytes(JPEG)
        self.original=(self.trained/'person_one'/'photo.jpg').read_bytes()
        self.manager=FaceManager(self.store,self.lock,lambda:[('person_one','photo.jpg')],
                                 self.trained,lambda img:(JPEG,vector()),lambda:None,lambda *a:{})

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_similar_faces_group_and_selected_assignment_preserves_rest(self):
        group=self.store.observe(vector(),JPEG,'camera_one')
        self.store.db.execute('UPDATE photos SET added=0')
        self.store.db.commit()
        self.assertEqual(group,self.store.observe(vector(),JPEG,'camera_two'))
        self.assertEqual(len(self.store.groups()[0]['photos']),2)
        selected=self.store.groups()[0]['photos'][0]
        self.manager.change('assign',{'group_id':group,'photo_ids':[selected],'name':'New Person'})
        self.assertEqual(len(self.store.embeddings()),1)
        self.assertEqual(len(self.store.groups()[0]['photos']),1)
        self.assertEqual(self.store.names()['new_person'],'New Person')

    def test_dissimilar_faces_separate_and_storage_is_bounded(self):
        self.store.max_groups=2
        for n in range(4):
            self.store.observe(vector(n),JPEG,'test')
            time.sleep(.002)
        self.assertEqual(len(self.store.groups()),2)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM photos').fetchone()[0],2)

    def test_expiry_removes_unknowns_but_not_enrollment(self):
        person=self.store.ensure_person('Known Person')
        self.store.add_photo(person,JPEG,vector(1))
        self.store.observe(vector(),JPEG,'test')
        self.store.db.execute('UPDATE groups SET last=0')
        self.store.db.commit()
        self.store.prune()
        self.assertEqual(self.store.groups(),[])
        self.assertEqual(len(self.store.embeddings()),1)

    def test_legacy_removal_hides_samples_without_changing_original_file(self):
        self.manager.change('remove-photo',{'photo_id':legacy_id('person_one','photo.jpg')})
        self.assertEqual(self.manager.state()['people'],[])
        self.assertEqual((self.trained/'person_one'/'photo.jpg').read_bytes(),self.original)
        self.store.close()
        self.store=ReviewStore(self.base)
        self.assertIn(('person_one','photo.jpg'),self.store.exclusions())

    def test_upload_and_rename_keep_stable_person_id(self):
        self.manager.change('upload',{'person_id':'person_one','image':base64.b64encode(JPEG).decode()})
        self.manager.change('rename',{'person_id':'person_one','name':'Display Name'})
        person=self.manager.state()['people'][0]
        self.assertEqual(person['id'],'person_one')
        self.assertEqual(person['name'],'Display Name')
        self.assertEqual(person['photo_count'],2)
        self.assertEqual((self.trained/'person_one'/'photo.jpg').read_bytes(),self.original)

    def test_photo_path_traversal_does_not_read_files(self):
        with self.assertRaises(ValueError):
            self.manager.photo('../../anything')

    def test_invalid_assignment_does_not_enroll(self):
        gid=self.store.observe(vector(),JPEG,'test')
        with self.assertRaises(ValueError):
            self.manager.change('assign',{'group_id':gid,'photo_ids':['not_in_group'],'name':'Nope'})
        self.assertEqual(self.store.embeddings(),[])
        self.assertEqual(self.store.names(),{})

    def test_camera_configuration_validates_entity_and_interval(self):
        for data in ({'entity':'http://example.invalid'},{'entity':'camera.test','interval':1}):
            with self.assertRaises(ValueError):
                self.manager.save_camera(data)
        self.manager.save_camera({'entity':'camera.test','name':'Test camera','interval':60})
        self.assertEqual(self.manager.cameras()[0]['interval'],60)

    def test_first_scan_after_camera_is_added_is_not_dropped(self):
        self.manager.recognize=lambda *args:{'success':True,'faces':[]}
        with patch('face_manager.supervisor',return_value=JPEG):
            self.manager.start()
            try:
                time.sleep(.05)
                self.manager.save_camera({'entity':'camera.new','name':'New camera','interval':0})
                self.manager.enqueue({'camera_entity':'camera.new'})
                for attempt in range(100):
                    if self.manager.camera_status.get('camera.new'):
                        break
                    time.sleep(.01)
                self.assertTrue(self.manager.camera_status['camera.new']['ok'])
            finally:
                self.manager.close()
                self.manager.thread.join(timeout=2)

    def test_ui_rejects_csrf_and_serves_photos_privately(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.manager))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        root='http://127.0.0.1:'+str(server.server_port)
        try:
            with urllib.request.urlopen(root+'/api/state') as response:
                state=json.load(response)
            payload=json.dumps({'person_id':'person_one','name':'Renamed'}).encode()
            req=urllib.request.Request(root+'/api/rename',data=payload,headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,403)
            req.add_header('X-CSRF-Token',state['csrf_token'])
            with urllib.request.urlopen(req) as response:
                self.assertTrue(json.load(response)['success'])
            with urllib.request.urlopen(root+'/api/photo/'+state['people'][0]['photos'][0]) as response:
                self.assertIn('no-store',response.headers['Cache-Control'])
                self.assertEqual(response.headers['Content-Type'],'image/jpeg')
            self.assertEqual(self.store.names()['person_one'],'Renamed')
        finally:
            server.shutdown()
            server.server_close()


class MQTTTests(unittest.TestCase):
    def test_discovery_event_payload_and_deduplication(self):
        class Client:
            def __init__(self):
                self.messages=[]
            def publish(self,topic,value,qos=0,retain=False):
                self.messages.append((topic,value,retain))
        state={'people':[{'id':'person_one','name':'Person One'}],'pending_groups':2,'cameras':[]}
        bridge=HomeAssistantBridge('synthetic',lambda:state,lambda cmd:None)
        bridge.client=Client()
        bridge.connected=True
        bridge.refresh()
        event_discovery=[json.loads(v) for t,v,r in bridge.client.messages if '/event/' in t]
        self.assertEqual(event_discovery[0]['event_types'],['recognized','unknown'])
        bridge.event('person_one','Person One',.8,'test_camera')
        bridge.event('person_one','Person One',.8,'test_camera')
        events=[(json.loads(v),r) for t,v,r in bridge.client.messages if t.endswith('/event')]
        self.assertEqual(len(events),1)
        self.assertFalse(events[0][1])
        self.assertEqual(events[0][0]['person_id'],'person_one')
        self.assertEqual(events[0][0]['camera'],'test_camera')
        state['people']=[]
        bridge.refresh()
        self.assertTrue(any(t.endswith('person_person_one/config') and v=='' and r for t,v,r in bridge.client.messages))


if __name__=='__main__':
    unittest.main()
