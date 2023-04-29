import network
import urequests
import utime as time
from robust2 import MQTTClient
import os
import gc
import sys
import json
import _thread
import machine
from machine import Pin

"""Custom class for Internet errors"""
class ConnectionError(Exception):
    pass


"""Setup GPIO error LED"""
errorLed = Pin(26,Pin.OUT)
errorLed.value(0)

"""*****Incircuit led control to indicate an error or when the programm exits****"""
led = machine.Pin("LED", machine.Pin.OUT)
led.off()

"""Hardware reset implementation(exit program when GP21 high) """
reset = machine.Pin(21,machine.Pin.IN,Pin.PULL_DOWN)

wifi = None

def setUpWifi():
    """******************* NET SET UP *************************"""
    global wifi 
    # WiFi connection information
     WIFI_SSID = 'YOUR WIFI ID NAME'
     WIFI_PASSWORD = 'YOUR WIFI PASSWORD'


    # turn off the WiFi Access Point
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)    
        
    # connect the device to the WiFi network
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    wifi.connect(WIFI_SSID, WIFI_PASSWORD)

    # wait until the device is connected to the WiFi network
    MAX_ATTEMPTS = 20
    attempt_count = 0
    while not wifi.isconnected() and attempt_count < MAX_ATTEMPTS:
        attempt_count += 1
        time.sleep(1)

    if attempt_count == MAX_ATTEMPTS:
        print('could not connect to the WiFi network')
        raise ConnectionError("No Network!")        
        
    else:
        print('connected')
        status = wifi.ifconfig()
        print( 'ip = ' + status[0] )
    time.sleep(3)
        
setUpWifi()
        
"""******************* NET SET UP FINISHED *************************""" 

#Global variables
reset = False
state = "OFF"
timer = "0"
time_progress = "0"
temp = "--"
timer_delay_last = 0


#Clients ID's (client's MAC address)
clients_ids = set()

#Setup GPIO to control the physical relay
relay = Pin(22,Pin.OUT)
relay.value(0)

#Configure to read Temperature sensor
sensor_temp = machine.ADC(4)
conversion_factor = 3.3 / (65535)


# create a random MQTT clientID 
random_num = int.from_bytes(os.urandom(3), 'little')
mqtt_client_id = bytes('client_'+str(random_num), 'utf-8')

# connect to Adafruit IO MQTT broker using unsecure TCP (port 1883)
# 
# To use a secure connection (encrypted) with TLS: 
#   set MQTTClient initializer parameter to "ssl=True"
#   Caveat: a secure connection uses about 9k bytes of the heap
#         (about 1/4 of the micropython heap on the ESP8266 platform)
ADAFRUIT_IO_URL = b'io.adafruit.com' 
ADAFRUIT_USERNAME = b'xxxxx'
ADAFRUIT_IO_KEY = b'xxxxxxxxxxxxxxxxxx'
CONTROL_FEED = "xxxxxx" #Use your own feed name
RESPONSE_FEED = "xxxxx" #Use your own feed name
FEED_CHECK_PERIOD_IN_SEC = 1 #1
TEMP_PUBLISH_PERIOD_IN_SEC = 10 #20

# format of feed name:  
#   "ADAFRUIT_USERNAME/feeds/ADAFRUIT_IO_FEEDNAME"
mqtt_control_feed = bytes('{:s}/feeds/{:s}'.format(ADAFRUIT_USERNAME, CONTROL_FEED), 'utf-8')

# format of feed name:  
#   "ADAFRUIT_USERNAME/feeds/ADAFRUIT_IO_FEEDNAME"
mqtt_response_feed = bytes('{:s}/feeds/{:s}'.format(ADAFRUIT_USERNAME, RESPONSE_FEED), 'utf-8')

"""*********************  FIREBASE SET UP ******************"""
serverToken='USE YOUR OWN FIREBASE SERVER TOKEN KEY'
"""*********************************************************"""
"""*********SEND PUSH NOTIFICATION TO ANDROID WITH FIREBASE CLOUD MESSAGING*************"""
notifData = "??"
sendNotif = False

def sendPushNotification():
    global serverToken,notifData
    
    headers = {
            'Content-Type': 'application/json',
            'Authorization': 'key=' + serverToken,
          }

    body = {
              'notification': {'title': 'Raspberry pico: Boiler',
                                'body': notifData
                                },
              'to':"/topics/YOUR TOPIC",
              #'priority': 'high',
              #'data': dataPayLoad,
            }
    try:        
        response = urequests.post("https://fcm.googleapis.com/fcm/send",headers = headers, data=json.dumps(body))
        #print (str(response.status_code))
        response.close()
        time.sleep(2)
    except Exception as e:        
        print ("FCM Error! " + str(e))

#Feed any changes to MQTT clients
def updateClient():
    global state,timer,temp,time_progress,client
    try:
        data = {
            "state" : state,
            "timer" : timer,
            "progress" : time_progress,
            "temp" : temp
            }
        print ("Sent to client: "+str(data))
        client.publish(mqtt_response_feed, json.dumps(data), qos=0)
    except Exception as e:
        print ("Update client error "+str(e))
    
#Register clients so the system feed MQTT to connected clients, otherwise save resources if no clients connected    
def registerClient(id,register):
    global clients_ids
    if register:
        if not id in clients_ids:
            clients_ids.add(id)
            #print ("Update client after registration!")            
            updateClient()
    else:
        if id in clients_ids:
            clients_ids.remove(id)
        
#Hardware controlling relay to switch device ON/OFF
def relayControl(tmr):
    try:
        global state,timer,temp,relay,time_progress,clients_ids,sendNotif,notifData,timer_delay_last,reset
        secsCount = 0
        broadcast = 10 #To broadcast updates to client every 10 mins
        secs = int(tmr)*60 #Activate for hours
        #secs = int(tmr) #For seconds
        state = "ON"
        relay.value(1) #Switch relay ON
        updateClient()
        notifData = "On for "+str(secs/3600)+" hrs, "+temp+" C"
        sendNotif = True
        while secsCount<=secs:
            time_now = time.time()
            if timer == "0" or reset:  #If client cancel the timer
                break;
            if (time_now - timer_delay_last) >=1.0:
               #time.sleep(1)
                secsCount+=1
                #print("Secs count: "+str(secsCount))
                time_progress = "{:.0f}".format(int(secsCount*100/secs)) #Time progress as percentage (to use on a progress bar)

            timer_delay_last = time_now
        
        relay.value(0)
        state = "OFF"
        time_progress = "0"
        timer = "0"
        timer_delay_last = 0
        #print ("Time up!")
        if not reset:
            notifData = "Off after "+"{0:.2f}".format(secsCount/3600)+" hrs, "+temp+" C"
            sendNotif = True        
            updateClient()
    except Exception as e:
        print ("Error on timer loop: "+str(e))
    
# The following function is the callback which is 
# called when subscribed data is received
def cb(topic, msg, retained, dup):
    global state,timer
    #print('Received Data:  Topic = {}, Msg = {}\n'.format(topic, msg)) 
    s = str(msg,'utf-8')
    jsonData = json.loads(s) #Encode to json data
    
    if "clientReg" in jsonData:  #Register client with its unique Id.
        id = str(jsonData["clientId"])
        register = eval(str(jsonData["clientReg"])) #Boolean True or False to register o de-register
        registerClient(id,register)
    
    if "timer" in jsonData:        #SetUp timer ON
        timer = str(jsonData["timer"])
        if int(timer) > 0:            
            _thread.start_new_thread(relayControl, (timer,))
            
    else:
        return
    
"""Check wifi connection"""    
def checkNet():
    global wifi,led
    flag = False
    #netCounter = 0
    if wifi is None:
        setUpWifi()
    while True:
        #Check internet connection and wifi adapter
        if wifi.isconnected():
            #print ("Net OK!")
            led.off()
            break
                
        else:                
            #print ("wifi disconnected!")
            led.on()
            wifi = None
            setUpWifi()       

"""Read the in-circuit temp sensor"""
def readTemp():
    global temp               
    reading = sensor_temp.read_u16() * conversion_factor 
    temperature = 27 - (reading - 0.706)/0.001721
    temp = "{0:.2f}".format(temperature)
    #print("Temp: "+temp)
    
"""******* Initialize MQTT Broker and subscribe to FEED ************"""
client = MQTTClient(client_id=mqtt_client_id, 
                    server=ADAFRUIT_IO_URL,
                    user=ADAFRUIT_USERNAME, 
                    password=ADAFRUIT_IO_KEY,
                    #keepalive=60,
                    ssl=False)

# Print diagnostic messages when retries/reconnects happens
client.DEBUG = True
# Information whether we store unsent messages with the flag QoS==0 in the queue.
client.KEEP_QOS0 = False
# Option, limits the possibility of only one unique message being queued.
client.NO_QUEUE_DUPS = True
# Limit the number of unsent messages in the queue.
client.MSG_QUEUE_MAX = 2

client.set_callback(cb)
# Connect to server, requesting not to clean session for this
# client. If there was no existing session (False return value
# from connect() method), we perform the initial setup of client
# session - subscribe to needed topics. Afterwards, these
# subscriptions will be stored server-side, and will be persistent,
# (as we use clean_session=False).
#
# TODO: Still exists???
# There can be a problem when a session for a given client exists,
# but doesn't have subscriptions a particular application expects.
# In this case, a session needs to be cleaned first. See
# example_reset_session.py for an obvious way how to do that.
#
# In an actual application, it's up to its developer how to
# manage these issues. One extreme is to have external "provisioning"
# phase, where initial session setup, and any further management of
# a session, is done by external tools. This allows to save resources
# on a small embedded device. Another extreme is to have an application
# to perform auto-setup (e.g., clean session, then re-create session
# on each restart). This example shows mid-line between these 2
# approaches, where initial setup of session is done by application,
# but if anything goes wrong, there's an external tool to clean session.
if not client.connect(clean_session=False):
    print("New session being set up")
    client.subscribe(mqtt_control_feed)
    led.on()
    time.sleep(3)
    led.off()
                    

"""******* FINISH Initialize Broker and subscribing to FEED ************"""

#Counter to send temp data every 10 secs
secsCount = 0
pingTimerCounter = 0
timer_main_loop = 0
conIssueCounter = 0


"""Main Loop"""
while True:
    try:                
        time_n_o_w = time.time()            
        if (time_n_o_w - timer_main_loop) >=FEED_CHECK_PERIOD_IN_SEC:
            checkNet()
            #print ("Second!")
            # At this point in the code you must consider how to handle
            # connection errors.  And how often to resume the connection.            
            if client.is_conn_issue():
                print ("Conn issue!")                
                while client.is_conn_issue():
                    time.sleep(2)
                    if conIssueCounter > 120:
                        conIssueCounter = 0
                        raise Exception("Reconnect Limit..!!")
                        #break
                    else:                        
                        conIssueCounter+=1
                        # If the connection is successful, the is_conn_issue
                        # method will not return a connection error.
                        print("reconnecting! "+str(conIssueCounter))                        
                        #raise Exception("")
                        client.reconnect()
                        time.sleep(2)
                else:
                    print("resubscribe!")
                    client.resubscribe()
                    time.sleep(2)
                    conIssueCounter = 0
                    
            else:
                errorLed.value(0)
                
                client.check_msg() # needed when publish(qos=1), ping(), subscribe()
                client.send_queue()  # needed when using the caching capabilities for unsent messages            
                
            
                readTemp()
                if secsCount > TEMP_PUBLISH_PERIOD_IN_SEC: #Update client every 10 secs
                    updateClient()
                    secsCount = 0
                if sendNotif is True:  #Send Notification if timer is off, cancelled or started.
                    print ("Sending notif!")
                    sendPushNotification() #Send FCM Notification when timer completed
                    sendNotif = False
                secsCount+=1
                """The below lines for hardware reset are optional"""
                #Hardware Reset(exit program)
        #         if reset.value():
        #             raise Exception("Reset Pressed!")
        #             print("Reset Pressed!")            
        timer_main_loop = time_n_o_w
    except (Exception, KeyboardInterrupt) as e:
        #print("disconnecting")
        if not isinstance(e, ConnectionError):
            client.disconnect()
        print("Main Error! "+str(e.__class__)+"  "+str(e))
        errorLed.value(1)
        time.sleep(10)
