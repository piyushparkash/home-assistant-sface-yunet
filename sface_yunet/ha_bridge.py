"""Supervisor API access and MQTT discovery. Credentials never reach the browser."""
from datetime import datetime, timezone
import json
import os
import threading
import time
import urllib.request


def supervisor(path, image=False):
    token=os.environ.get('SUPERVISOR_TOKEN')
    if not token:
        raise RuntimeError('Home Assistant is available only inside the app')
    request=urllib.request.Request('http://supervisor'+path,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=20) as response:
        payload=response.read(8*1024*1024+1)
    if len(payload)>8*1024*1024:
        raise ValueError('Home Assistant response is too large')
    return payload if image else json.loads(payload)


class HomeAssistantBridge:
    def __init__(self, instance, snapshot, command, enabled=True):
        self.root='sface/'+instance
        self.instance=instance
        self.snapshot=snapshot
        self.command=command
        self.enabled=enabled
        self.connected=False
        self.status='Connecting to MQTT' if enabled else 'MQTT discovery disabled'
        self.client=None
        self.stop_event=threading.Event()
        self.last_events={}
        self.discovered=set()
        self.thread=threading.Thread(target=self._worker,daemon=True)

    def start(self):
        if self.enabled:
            self.thread.start()

    def publish(self, topic, value, retain=False):
        if self.client and self.connected:
            self.client.publish(self.root+'/'+topic,
                                json.dumps(value) if not isinstance(value,str) else value,
                                qos=1,retain=retain)

    def discovery(self, component, key, name, **settings):
        unique='sface_'+self.instance+'_'+key
        config={'name':name,'unique_id':unique,
                'default_entity_id':component+'.sface_'+key,
                'availability_topic':self.root+'/availability',
                'device':{'identifiers':['sface_'+self.instance],'name':'SFace face recognition',
                          'manufacturer':'Community','model':'YuNet + SFace','sw_version':'1.1.0'},
                **settings}
        self.client.publish('homeassistant/'+component+'/'+unique+'/config',json.dumps(config),qos=1,retain=True)
        self.discovered.add((component,key))

    def refresh(self):
        if not self.connected:
            return
        state=self.snapshot()
        names=state['people']
        self.discovery('sensor','known_people','Known people',state_topic=self.root+'/counts',value_template='{{ value_json.people }}',icon='mdi:account-group')
        self.discovery('sensor','pending_groups','Pending face groups',state_topic=self.root+'/counts',value_template='{{ value_json.groups }}',icon='mdi:account-question')
        self.discovery('sensor','last_recognized','Last recognized person',state_topic=self.root+'/last',value_template='{{ value_json.display_name }}',json_attributes_topic=self.root+'/last',icon='mdi:face-recognition')
        self.discovery('event','recognition','Recognition',state_topic=self.root+'/event',event_types=['recognized','unknown'])
        wanted=set()
        for person in names:
            key='person_'+person['id']
            wanted.add(('binary_sensor',key))
            self.discovery('binary_sensor',key,person['name']+' recently seen',
                           state_topic=self.root+'/person/'+person['id'],off_delay=120,device_class='occupancy')
        for camera in state.get('cameras',[]):
            key='scan_'+camera['entity'].replace('.','_')
            wanted.add(('button',key))
            self.discovery('button',key,'Scan '+camera['name'],command_topic=self.root+'/command',
                           payload_press=json.dumps({'camera_entity':camera['entity']}),icon='mdi:camera')
        for component,key in list(self.discovered):
            if component in ('binary_sensor','button') and (component,key) not in wanted:
                self.client.publish('homeassistant/'+component+'/sface_'+self.instance+'_'+key+'/config','',qos=1,retain=True)
                self.discovered.discard((component,key))
        self.publish('counts',{'people':len(names),'groups':state['pending_groups']},retain=True)

    def event(self, person, name, score, camera, group=None):
        if not self.connected:
            return
        key=(camera,person or group)
        now=time.time()
        if now-self.last_events.get(key,0)<15:
            return
        self.last_events[key]=now
        self.last_events={k:v for k,v in self.last_events.items() if now-v<300}
        payload={'event_type':'recognized' if person else 'unknown','person_id':person,
                 'display_name':name,'score':round(float(score or 0),4),'camera':camera,
                 'group_id':group,'timestamp':datetime.now(timezone.utc).isoformat()}
        self.publish('event',payload)
        if person:
            self.publish('last',payload,retain=True)
            self.publish('person/'+person,'ON')

    def _worker(self):
        while not self.stop_event.is_set():
            try:
                import paho.mqtt.client as mqtt
                config=supervisor('/services/mqtt')['data']
                client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='sface_'+self.instance)
                self.client=client
                client.username_pw_set(config['username'],config['password'])
                client.will_set(self.root+'/availability','offline',qos=1,retain=True)
                def connected(client,userdata,flags,reason,properties):
                    self.connected=not reason.is_failure
                    if self.connected:
                        self.status='Connected to Home Assistant MQTT'
                        client.subscribe('homeassistant/status',qos=1)
                        client.subscribe(self.root+'/command',qos=1)
                        self.refresh()
                        for person in self.snapshot()['people']:
                            self.publish('person/'+person['id'],'OFF')
                        self.publish('availability','online',retain=True)
                def disconnected(client,userdata,flags,reason,properties):
                    self.connected=False
                    self.status='MQTT disconnected; reconnecting'
                def message(client,userdata,msg):
                    if msg.topic=='homeassistant/status' and msg.payload==b'online':
                        self.refresh()
                    elif msg.topic==self.root+'/command' and not msg.retain:
                        try:
                            self.command(json.loads(msg.payload))
                        except (ValueError,TypeError):
                            pass
                client.on_connect=connected
                client.on_disconnect=disconnected
                client.on_message=message
                if config.get('ssl'):
                    client.tls_set()
                client.connect_async(config['host'],int(config['port']),keepalive=30)
                client.loop_start()
                while not self.stop_event.wait(30):
                    if self.connected:
                        self.refresh()
                break
            except Exception:
                self.status='MQTT unavailable. Install Mosquitto broker and set up the MQTT integration.'
                if self.client:
                    self.client.loop_stop()
                self.stop_event.wait(30)

    def close(self):
        self.stop_event.set()
        if self.client:
            if self.connected:
                info=self.client.publish(self.root+'/availability','offline',qos=1,retain=True)
                try:
                    info.wait_for_publish(timeout=2)
                except RuntimeError:
                    pass
            self.client.disconnect()
            self.client.loop_stop()
