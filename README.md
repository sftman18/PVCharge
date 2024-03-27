# PVCharge

An adaptive charging controller for your Tesla, enabling you to direct excess solar energy to your car.

## Requirements
- <a href="https://www.tesla.com/">Tesla vehicle</a>
- Configured <a href="https://github.com/teslamotors/vehicle-command">Tesla Vehicle Command SDK</a> environment with <a href="https://github.com/teslamotors/vehicle-command/tree/main/cmd/tesla-control">tesla-control</a> available
- <a href="https://github.com/teslamate-org/teslamate">TeslaMate</a>
- <a href="https://www.egauge.net">eGauge solar monitoring</a> with a CT on the charger circuit
- Linux computer with Bluetooth, such as a <a href="https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/">Raspberry Pi Zero 2 W</a>

## Optional
- <a href="https://www.home-assistant.io/">Home Assistant</a> or another <a href="https://apps.apple.com/us/app/mqttool/id1085976398">MQTT client</a> to adjust the options for after-dark charging, and delayed charging<br><br>

## Tesla Vehicle Command SDK

PVCharge uses <a href="https://github.com/teslamotors/vehicle-command/tree/main/cmd/tesla-control">tesla-control</a> in the <a href="https://github.com/teslamotors/vehicle-command">Tesla Vehicle Command SDK</a> to communicate with your car over local Bluetooth

Here are a few hints to help complete the tesla-control installation

<pre>Create the directory "keyrings" to hold your private key:
mkdir /home/pi/.local/share/keyrings

Setting the key:
tesla-keygen -key-file /home/pi/.local/share/keyrings/private_key.pem create > public_key.pem

While in the car, pair with this command:
tesla-control -ble add-key-request public_key.pem owner cloud_key</pre>

## PVCharge Installation
- Install Python (3.11+) and Git using your package manager<br>
- Clone the repo <pre>git clone https://github.com/sftman18/PVCharge.git</pre>
- In the PVCharge directory, configure the Python virtual environment and install the requirements
<pre>python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt</pre>

## Configuration
- Create your own copy of example.env, and example_config.toml
<pre>cp example.env .env
cp example_config.toml config.toml
Change all values to match your equipment settings and preferences</pre>
- Copy included PVCharge.service to the proper path (systemd shown)
<pre>sudo cp PVCharge.service /etc/systemd/system/</pre>
- Activate the service and start it:
<pre>sudo systemctl enable PVCharge.service
sudo systemctl start PVCharge.service</pre>
- Check to ensure it is running:
<pre>sudo systemctl status PVCharge.service</pre>

## Usage
PVCharge waits for 3 conditions to be communicated over MQTT from <a href="https://docs.teslamate.org/docs/integrations/mqtt">Teslamate</a>
- Car location is "Home" <code>teslamate/cars/$car_id/geofence</code>
- Car is plugged in <code>teslamate/cars/$car_id/plugged_in</code>
- Car battery level is below the App limit <code>teslamate/cars/$car_id/battery_level</code><br>
#### When those conditions are satisfied, it will attempt to start charging, when solar energy is available
#### As PV output changes throughout the day, charging rate will be adjusted to use the excess energy

## Status
PVCharge publishes status on MQTT
- Charging report <code>topic_base/status</code>
- Current charge rate <code>topic_base/new_charge_rate</code>

## Control
- The behavior of after-hours charging is controlled by MQTT: <code>topic_base/prevent_non_solar_charging</code><br>
<dl>
  <dt>True</dt> <dd>PVCharge will prevent charging when insufficient PV output is available</dd>
  <dt>False</dt> <dd>PVCharge will ignore charging when insufficient PV output is available (default, Configurable in config.toml)</dd>
</dl><br>

- The ability to delay charging is controlled by: <code>topic_base/charge_delay</code><br>
<dl>
  <dt>"delay"</dt> <dd>charging is delayed for 1 hour</dd>
  <dt>"##" (number)</dt> <dd>charging is delayed by the indicated number of minutes</dd>
  <dt>other text (i.e. "cancel")</dt> <dd>resume normal charging</dd>
</dl>

## Troubleshooting
Enable more verbose logging by changing the LOG_LEVEL to DEBUG in config.toml<br>
- Check PVCharge.log for any unexpected output

## Screenshot of adaptive charging seen through eGauge
<img src="energy_graph.png" alt="PV Energy Graph">
