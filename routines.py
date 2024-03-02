import os
import sys
import subprocess
import math
import time
import logging
import tomllib
from dotenv import load_dotenv
from egauge import webapi
from egauge.webapi.device import Register, Local
import paho.mqtt.client as mqtt


# Load parameters from .env
load_dotenv()
# Load config file
with open("config.toml", mode="rb") as fp:
    config = tomllib.load(fp)


class PowerUsage:
    """Class to request data from the eGauge web API"""
    def __init__(self):
        # Load parameters from .env
        self.meter_dev = os.getenv("EGDEV")
        self.meter_user = os.getenv("EGUSR")
        self.meter_password = os.getenv("EGPWD")
        self.eGauge_gen = os.getenv("EGAUGE_GEN")
        self.eGauge_use = os.getenv("EGAUGE_USE")
        self.eGauge_charger = os.getenv("EGAUGE_CHARGER")
        self.eGauge_charger_sensor = os.getenv("EGAUGE_CHARGER_SENSOR")
        self.register_sample = 0
        self.sensor_sample = 0
        self.generation_reg = 0
        self.usage_reg = 0
        self.tesla_charger_reg = 0
        self.charge_rate_sensor = 0
        self.charger_voltage_sensor = 0
        self.new_charge_rate = 0

        # Initialize eGauge
        self.my_eGauge = webapi.device.Device(self.meter_dev, webapi.JWTAuth(self.meter_user, self.meter_password))

        # verify we can talk to the meter:
        try:
            rights = self.my_eGauge.get("/auth/rights").get("rights", [])
        except webapi.Error as e:
            logging.critical(f"Sorry, failed to connect to {self.meter_dev}: {e}")
            sys.exit(1)
        logging.info(f"Connected to eGauge {self.meter_dev} (user {self.meter_user}, rights={rights})")

    def sample_register(self):
        """Sample registers and convert kW to W"""
        self.register_sample = Register(self.my_eGauge, {"rate": "True", "time": "now"})
        self.generation_reg = self.register_sample.pq_rate(self.eGauge_gen).value * 1000
        logging.debug(f"   Generation reg: {self.generation_reg}")
        self.usage_reg = self.register_sample.pq_rate(self.eGauge_use).value * 1000
        logging.debug(f"        Usage reg: {self.usage_reg}")
        self.tesla_charger_reg = self.register_sample.pq_rate(self.eGauge_charger).value * 1000
        logging.debug(f"Tesla charger reg: {self.tesla_charger_reg}")

    def sample_sensor(self):
        self.sensor_sample = Local(self.my_eGauge, "l=L1:L2&s=all")
        self.charger_voltage_sensor = (self.sensor_sample.rate("L1", "n") +
                                       self.sensor_sample.rate("L2", "n"))
        logging.debug(f"Charger voltage sensor: {self.charger_voltage_sensor}")
        self.charge_rate_sensor = self.sensor_sample.rate(self.eGauge_charger_sensor, "n")
        logging.debug(f"    Charge rate sensor: {self.charge_rate_sensor}")

    def calculate_charge_rate(self, new_sample):
        if new_sample:
            self.sample_register()
            self.sample_sensor()
        # Calculate the charge rate
        self.new_charge_rate = ((self.generation_reg - (self.usage_reg - self.tesla_charger_reg)) /
                                self.charger_voltage_sensor)
        logging.debug(f"New charge rate: {self.new_charge_rate}")
        return self.new_charge_rate

    def verify_new_charge_rate(self, new_charge_rate):
        for attempts in range(0, 5):
            self.sample_sensor()
            # Use round() on the verify step (vs math.floor()) to prevent constant requests for the same value
            if round(self.charge_rate_sensor) >= new_charge_rate:
                logging.debug(f"New charge rate verified")
                return True
            time.sleep(0.5)
        logging.debug(f"New charge rate NOT verified")
        return False

    def sufficient_generation(self, min_charge):
        charge_rate = math.floor(self.calculate_charge_rate(new_sample=True))
        logging.debug(f"New charge rate (floor): {charge_rate}")
        if charge_rate >= min_charge:
            return True
        else:
            return False

    def status_report(self, charge_tesla, car_is_charging, new_sample):
        if new_sample:
            self.calculate_charge_rate(new_sample)
        # Build status string
        status = "Status: "
        if charge_tesla:
            status += "En:1 "
        else:
            status += "En:0 "
        if car_is_charging:
            status += "Chg:1 "
        else:
            status += "Chg:0 "
        status += ("Cur:" + str(round(self.charge_rate_sensor)) + " " + "New:" +
                   str(math.floor(self.new_charge_rate)))
        return status


class TeslaCommands:
    """Class to handle commands sent to Tesla Vehicle Command SDK"""
    def __init__(self):
        # Load parameters from .env
        self.tesla_control_bin = os.getenv("TESLA_CONTROL_BIN")
        self.tesla_key_file = os.getenv("TESLA_KEY_FILE")
        self.tesla_base_command = [self.tesla_control_bin, '-ble', '-key-file', self.tesla_key_file]
        # Test for existence of tesla-control
        if not os.path.exists(self.tesla_control_bin):
            logging.critical(f"tesla-control not found at: {self.tesla_control_bin}")
            logging.critical("Please point to it in .env, or install it from:")
            logging.critical("https://github.com/teslamotors/vehicle-command/tree/main/cmd/tesla-control")
            sys.exit(1)

    def set_charge_rate(self, charge_rate):
        command = self.tesla_base_command + ['charging-set-amps']
        command.append(str(charge_rate))
        logging.debug(command)
        return call_sub_error_handler(command)

    def start_charging(self):
        command = self.tesla_base_command + ['charging-start']
        logging.debug(command)
        return call_sub_error_handler(command)

    def stop_charging(self):
        command = self.tesla_base_command + ['charging-stop']
        logging.debug(command)
        return call_sub_error_handler(command)

    def wake(self):
        command = self.tesla_base_command + ['-domain', 'vcsec', 'wake']
        logging.debug(command)
        return call_sub_error_handler(command)


def call_sub_error_handler(cmd):
    try:
        result = subprocess.run(args=cmd, capture_output=True, text=True, check=True)
        if result.stdout != "":
            logging.debug(result.stdout)
    except subprocess.CalledProcessError as error:
        logging.warning(f"{type(error).__name__} - {error}")
        logging.warning(f"Error: {error.stderr}")
        return False
    return True

def check_elapsed_time(loop_time, compare_time, wait_time):
    if compare_time == 0:
        compare_time = time.time()    # Set counter to current time
        return False, compare_time
    elif (loop_time - compare_time) >= wait_time:
        # Compare current loop time to first time
    	return True, compare_time
    else:
        # We haven't waited long enough, keep waiting
    	return False, compare_time


class MqttCallbacks:
    """Class to handle MQTT"""
    def __init__(self):
        # Load parameters from .env
        self.broker = os.getenv("BROKER")
        self.port = int(os.getenv("PORT"))
        self.client_id = os.getenv("CLIENT_ID")
        self.topic_prevent_non_solar_charge = config["TOPIC_PREVENT_NON_SOLAR_CHARGE"]
        self.topic_teslamate_geofence = config["TOPIC_TESLAMATE_GEOFENCE"]
        self.topic_teslamate_plugged_in = config["TOPIC_TESLAMATE_PLUGGED_IN"]
        self.topic_teslamate_battery_level = config["TOPIC_TESLAMATE_BATTERY_LEVEL"]
        self.topic_teslamate_charge_limit_soc = config["TOPIC_TESLAMATE_CHARGE_LIMIT_SOC"]
        self.topic_teslamate_state = config["TOPIC_TESLAMATE_STATE"]
        self.max_charge_limit = config["MAX_CHARGE_LIMIT"]
        if config["PREVENT_NON_SOLAR_CHARGE"] == "True":
            self.var_topic_prevent_non_solar_charge = True
        else:
            self.var_topic_prevent_non_solar_charge = False
        self.var_topic_teslamate_geofence = False
        self.var_topic_teslamate_plugged_in = False
        self.var_topic_teslamate_battery_level = 0
        self.var_topic_teslamate_charge_limit_soc = 0
        self.var_topic_teslamate_state = False

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id, protocol=mqtt.MQTTv311,
                                  clean_session=True)
        self.client.on_connect = self.on_connect
        self.client.message_callback_add(self.topic_prevent_non_solar_charge, self.on_message_prevent_non_solar_charge)
        self.client.message_callback_add(self.topic_teslamate_geofence, self.on_message_geofence)
        self.client.message_callback_add(self.topic_teslamate_plugged_in, self.on_message_plugged_in)
        self.client.message_callback_add(self.topic_teslamate_battery_level, self.on_message_battery_level)
        self.client.message_callback_add(self.topic_teslamate_charge_limit_soc, self.on_message_charge_limit_soc)
        self.client.message_callback_add(self.topic_teslamate_state, self.on_message_state)
        self.client.connect(host=self.broker, port=self.port, keepalive=60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logging.critical(f"Failed to connect, return code {reason_code}\n")
            sys.exit(1)
        self.client.subscribe(topic=self.topic_prevent_non_solar_charge, qos=1)
        logging.debug(f"Subscribed to: {self.topic_prevent_non_solar_charge}")
        self.client.subscribe(topic=self.topic_teslamate_geofence, qos=1)
        logging.debug(f"Subscribed to: {self.topic_teslamate_geofence}")
        self.client.subscribe(topic=self.topic_teslamate_plugged_in, qos=1)
        logging.debug(f"Subscribed to: {self.topic_teslamate_plugged_in}")
        self.client.subscribe(topic=self.topic_teslamate_battery_level, qos=1)
        logging.debug(f"Subscribed to: {self.topic_teslamate_battery_level}")
        self.client.subscribe(topic=self.topic_teslamate_charge_limit_soc, qos=1)
        logging.debug(f"Subscribed to: {self.topic_teslamate_charge_limit_soc}")
        self.client.subscribe(topic=self.topic_teslamate_state, qos=1)
        logging.debug(f"Subscribed to: {self.topic_teslamate_state}")

    def on_message_prevent_non_solar_charge(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        if msg.payload.decode("utf-8") == "True":
            self.var_topic_prevent_non_solar_charge = True
        else:  # All messages not matching "True" mapped to "False"
            self.var_topic_prevent_non_solar_charge = False

    def on_message_geofence(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        if msg.payload.decode("utf-8") == "Home":
            self.var_topic_teslamate_geofence = True
        else:  # All messages not matching "Home" mapped to "False"
            self.var_topic_teslamate_geofence = False

    def on_message_plugged_in(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        if msg.payload.decode("utf-8") == "true":
            self.var_topic_teslamate_plugged_in = True
        else:
            self.var_topic_teslamate_plugged_in = False

    def on_message_battery_level(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        self.var_topic_teslamate_battery_level = int(msg.payload.decode("utf-8"))

    def on_message_charge_limit_soc(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        self.var_topic_teslamate_charge_limit_soc = int(msg.payload.decode("utf-8"))

    def on_message_state(self, client, userdata, msg):
        logging.debug(msg.payload.decode('utf-8'))
        self.var_topic_teslamate_state = msg.payload.decode("utf-8")

    def calculate_charge_tesla(self):
        # Charge if: Car is at Home, Car is plugged in, and battery < max_charge_limit
        if (self.var_topic_teslamate_geofence & self.var_topic_teslamate_plugged_in &
                (self.var_topic_teslamate_battery_level < self.max_charge_limit)):
            return True
        else:
            return False
