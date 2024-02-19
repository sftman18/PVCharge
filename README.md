# PVCharge

# PVCharge adjusts charging rate based on generated solar energy

<img src="energy_graph.png" alt="PV Energy Graph">

## Requirements:
* Tesla vehicle
* <a href="https://github.com/teslamate-org/teslamate">TeslaMate</a>
* <a href="https://www.egauge.net">eGauge solar monitoring, with a CT on the charger circuit</a>
* Linux computer with Bluetooth, such as a <a href="https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/">Raspberry Pi Zero 2 W</a>

## Optional:
* <a href="https://www.home-assistant.io/">Home Assistant</a> or another <a href="https://apps.apple.com/us/app/mqttool/id1085976398">MQTT client</a> to adjust the MQTT option for after-dark charging

## Tesla Vehicle Command SDK

PVCharge uses the <a href="https://github.com/teslamotors/vehicle-command">Tesla Vehicle Command SDK</a>, to communicate with your car over local Bluetooth

Note: To support Waking over BLE, please apply this <a href="https://github.com/teslamotors/vehicle-command/pull/106">PR:106</a>

Here are a few hints to help complete the tesla-command installation:

<pre>Create the directory "keyrings" to hold your private key
mkdir /home/pi/.local/share/keyrings

Setting the key
tesla-keygen -key-file /home/pi/.local/share/keyrings/private_key.pem create > public_key.pem

While in the car, pair with this command:
tesla-control -ble add-key-request public_key.pem owner cloud_key</pre>

## PVCharge Installation
<pre>Install a few essential libraries:
sudo apt install python-pip git
git clone https://github.com/sftman18/PVCharge.git
In the PVCharge directory:
sudo pip install -r requirements.txt</pre>

## Configuration
Create your own copy of example.env
<pre>cp example.env .env
Change all values to match your equipment settings</pre>
Copy included PVCharge.service to the proper path (systemd shown)
<pre>sudo cp PVCharge.service /etc/systemd/system/</pre>
Activate the service and start it:
<pre>sudo systemctl enable PVCharge.service
sudo systemctl start PVCharge.service</pre>
Check to ensure it is running:
<pre>sudo systemctl status PVCharge.service</pre>