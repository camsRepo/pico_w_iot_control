# pico_w_iot_control
Raspberry pico W power control using MQTT, Firebase Cloud Messaging(FCM) and Adafruit IO feeds. 

# Introduction
Pico w iot control is aproject aim to control any electronic/electric device with the use of MQTT communication system under the Adafruit IO platform sending data through the net to multiple clients subscribed to a topic(feeds), this data could be from a sensor or simply on/off signals. In this particular case Firebase messaging is used to sent push notifications to mobile phones or any implementation of the FCM api.

# Functionality 
The objective of this project is to control a relay module with a raspberry pico w through the net using a mobile phone (Android). The Raspberry pico w is reading temperature data from it's own temp sensor and feeding it back to the broker(MQTT server) on the main thread. On a second thread the pico is listening to data from the clients to switch relay on/off setting up a timer. As mentioned before the broker(Server) is base on the Adafruit IO platform.

The graphic interface is an Android app that implemets a MQTT api to send/receibe data from broker and FCM api to receive notifications.
