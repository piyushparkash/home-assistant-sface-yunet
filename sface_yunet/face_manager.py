"""Face management using overlays; never rewrites legacy enrollment files."""
import base64
import hashlib
from pathlib import Path
import queue
import re
import threading
import time

import cv2
import numpy as np

from ha_bridge import supervisor


def legacy_id(person, filename):
    return 'legacy_'+hashlib.sha256((person+'\0'+filename).encode()).hexdigest()[:32]


class FaceManager:
    def __init__(self, store, lock, legacy, trained, vectorize, rebuild, recognize):
        self.store,self.lock,self.legacy,self.trained=store,lock,legacy,Path(trained)
        self.vectorize,self.rebuild,self.recognize=vectorize,rebuild,recognize
        self.bridge=None
        self.commands=queue.Queue(maxsize=8)
        self.stop_event=threading.Event()
        self.camera_status={}
        self.next_scan={}
        self.thread=threading.Thread(target=self._worker,daemon=True)

    def cameras(self):
        with self.store.lock:
            row=self.store.db.execute("SELECT value FROM settings WHERE key='cameras'").fetchone()
            import json
            return json.loads(row[0]) if row else []

    def state(self):
        with self.lock:
            names=self.store.names()
            legacy={}
            excluded=self.store.exclusions()
            for person,filename in self.legacy():
                if (person,filename) not in excluded:
                    legacy.setdefault(person,[]).append(legacy_id(person,filename))
            people=[]
            for person in sorted(set(names)|set(legacy)):
                photos=legacy.get(person,[])+self.store.known_photos(person)
                people.append({'id':person,'name':names.get(person,person.replace('_',' ').title()),
                               'photos':photos,'photo_count':len(photos)})
            groups=self.store.groups()
            return {'people':people,'groups':groups,'pending_groups':len(groups),
                    'cameras':self.cameras(),'camera_status':dict(self.camera_status),
                    'mqtt':self.bridge.status if self.bridge else 'Not started',
                    'mqtt_connected':bool(self.bridge and self.bridge.connected),
                    'mqtt_topic':self.bridge.root if self.bridge else '',
                    'retention_days':self.store.retention_days,'max_groups':self.store.max_groups}

    def photo(self, photo_id):
        with self.lock:
            if photo_id.startswith('legacy_'):
                for person,filename in self.legacy():
                    if legacy_id(person,filename)==photo_id and (person,filename) not in self.store.exclusions():
                        path=(self.trained/person/filename).resolve()
                        if not path.is_relative_to(self.trained.resolve()):
                            break
                        image=cv2.imread(str(path))
                        if image is not None:
                            h,w=image.shape[:2]
                            if max(h,w)>512:
                                image=cv2.resize(image,(round(w*512/max(h,w)),round(h*512/max(h,w))))
                            return cv2.imencode('.jpg',image)[1].tobytes()
                raise ValueError('Photo not available')
            return self.store.photo(photo_id)

    def change(self, action, data):
        with self.lock:
            current=self.state()
            ids={p['id'] for p in current['people']}
            person=data.get('person_id')
            if action in ('upload','assign'):
                if person and person not in ids:
                    raise ValueError('Choose an existing person or enter a new name')
                name=data.get('name','').strip()
                if not person and (not name or len(name)>80):
                    raise ValueError('Enter a name or select an existing person')
                if action=='upload':
                    try:
                        raw=base64.b64decode(data.get('image',''),validate=True)
                    except Exception:
                        raise ValueError('Select a valid JPEG or PNG photo')
                    if len(raw)>8*1024*1024:
                        raise ValueError('Choose an image smaller than 8 MiB')
                    image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
                    if image is None or image.size>60_000_000:
                        raise ValueError('Image cannot be read or is too large')
                    jpeg,vector=self.vectorize(image)
                    person=person or self.store.ensure_person(name)
                    if person not in self.store.names():
                        self.store.ensure_person(next(p['name'] for p in current['people'] if p['id']==person),person)
                    if len(self.store.known_photos(person))>=100:
                        raise ValueError('A person can have at most 100 uploaded photos')
                    self.store.add_photo(person,jpeg,vector)
                else:
                    gid=data.get('group_id')
                    photos=data.get('photo_ids',[])
                    group=next((g for g in current['groups'] if g['id']==gid),None)
                    if not group or not photos or not set(photos).issubset(set(group['photos'])):
                        raise ValueError('Select clear photos from this group')
                    person=person or self.store.ensure_person(name)
                    if person not in self.store.names():
                        self.store.ensure_person(next(p['name'] for p in current['people'] if p['id']==person),person)
                    if len(self.store.known_photos(person))+len(photos)>100:
                        raise ValueError('A person can have at most 100 uploaded photos')
                    self.store.assign(gid,photos,person)
            elif action=='rename':
                if person not in ids:
                    raise ValueError('Person not found')
                self.store.rename(person,data.get('name',''))
            elif action=='remove-photo':
                photo=data.get('photo_id','')
                known={v for p in current['people'] for v in p['photos']}
                if photo not in known:
                    raise ValueError('Photo not found')
                if photo.startswith('legacy_'):
                    for pid,filename in self.legacy():
                        if legacy_id(pid,filename)==photo:
                            self.store.exclude(pid,filename)
                            break
                else:
                    self.store.remove_photo(photo)
            elif action=='remove-person':
                if person not in ids:
                    raise ValueError('Person not found')
                for pid,filename in self.legacy():
                    if pid==person:
                        self.store.exclude(pid,filename)
                self.store.remove_person(person)
            elif action=='dismiss':
                self.store.dismiss(data.get('group_id',''))
            else:
                raise ValueError('Unknown action')
            self.rebuild()
        if self.bridge:
            self.bridge.refresh()
        return {'success':True}

    def available_cameras(self):
        states=supervisor('/core/api/states')
        return [{'entity':s['entity_id'],'name':s.get('attributes',{}).get('friendly_name',s['entity_id'])}
                for s in states if re.fullmatch(r'camera\.[a-z0-9_]+',s.get('entity_id',''))]

    def save_camera(self,data):
        import json
        entity=str(data.get('entity',''))
        if not re.fullmatch(r'camera\.[a-z0-9_]+',entity):
            raise ValueError('Choose a Home Assistant camera')
        with self.lock:
            cameras=[c for c in self.cameras() if c['entity']!=entity]
            if not data.get('remove'):
                if len(cameras)>=8:
                    raise ValueError('At most eight cameras are supported')
                name=str(data.get('name','')).strip()[:64] or entity.split('.',1)[1]
                interval=int(data.get('interval',0))
                if interval not in (0,30,60,120,300):
                    raise ValueError('Choose a supported scan interval')
                cameras.append({'entity':entity,'name':name,'interval':interval})
            with self.store.lock,self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO settings VALUES ('cameras',?)",(json.dumps(cameras),))
        if self.bridge:
            self.bridge.refresh()

    def enqueue(self,data):
        entity=data.get('camera_entity')
        if entity not in {c['entity'] for c in self.cameras()}:
            raise ValueError('Configure this camera first')
        try:
            self.commands.put_nowait(entity)
        except queue.Full:
            raise ValueError('Scan queue is full. Try again shortly.')

    def _worker(self):
        last_prune=0
        while not self.stop_event.is_set():
            if time.time()-last_prune>=60:
                self.store.prune()
                last_prune=time.time()
            cameras=self.cameras()
            for camera in cameras:
                if camera['interval'] and time.time()>=self.next_scan.get(camera['entity'],0):
                    try:
                        self.enqueue({'camera_entity':camera['entity']})
                    except ValueError:
                        pass
                    self.next_scan[camera['entity']]=time.time()+camera['interval']
            try:
                entity=self.commands.get(timeout=1)
            except queue.Empty:
                continue
            try:
                camera=next((c for c in self.cameras() if c['entity']==entity),None)
                if not camera:
                    continue
                image=supervisor('/core/api/camera_proxy/'+entity,image=True)
                with self.lock:
                    result=self.recognize(image,camera['name'])
                self.camera_status[entity]={'ok':bool(result.get('success')),'at':time.time(),
                                            'faces':len(result.get('faces',[]))}
            except Exception:
                self.camera_status[entity]={'ok':False,'at':time.time(),
                                            'error':'Camera snapshot unavailable. Check the camera entity and app permissions.'}

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
