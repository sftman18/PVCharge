import os
import math
import time
import logging
import tomllib
import routines

# Load config file
with open("config.toml", mode="rb") as fp:
    config = tomllib.load(fp)

logging.basicConfig(
    filename=config["LOG_FILE"],
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
if config["LOG_LEVEL"] == "INFO":
    logging.getLogger().setLevel(logging.INFO)
elif config["LOG_LEVEL"] == "DEBUG":
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.warning("Unknown logging level")


# Initialize classes
Energy = routines.PowerUsage()
Car = routines.TeslaCommands()
Messages = routines.MqttCallbacks()

# Control loop variables
car_is_charging = False
stop_charging_time = 0
start_charging_time = 0
report_time = time.time() - config["REPORT_DELAY"]
while True:
    # Record loop start time
    loop_time = time.time()
    # Check if we are allowed to charge
    charge_tesla = Messages.calculate_charge_tesla()
    sun_up = Energy.check_sun_up()
    charge_delay = Messages.calculate_charge_delay(loop_time)
    logging.debug(f"Current calculated charge enable: {charge_tesla}")
    logging.debug(f"                      Is Sun Up?: {sun_up}")
    prevent_non_solar_charge = Messages.var_topic_prevent_non_solar_charge
    logging.debug(f"Current prevent non_solar charge: {prevent_non_solar_charge}")

    if ((charge_tesla and sun_up) and not charge_delay):    # If we are allowed to charge
        if car_is_charging:    # Is the car currently charging?
            if Energy.sufficient_generation(config["MIN_CHARGE"]):
                # Reset stop time
                stop_charging_time = 0
                # Calculate new charge rate
                # Use math.floor() on calculate_charge_rate to ensure we are always just "under" the available PV generation capacity
                # Use round() on charge_rate_sensor to prevent constant requests when on the edge of a value
                new_charge_rate = math.floor(Energy.calculate_charge_rate(new_sample=False))
                logging.debug(f"Car charging, new rate calculated: {new_charge_rate}, current rate: {round(Energy.charge_rate_sensor)}")
                if new_charge_rate != round(Energy.charge_rate_sensor):
                    # Set new charge rate
                    if Car.set_charge_rate(new_charge_rate):
                        if Energy.verify_new_charge_rate(new_charge_rate):
                            logging.info(f"Car charging, new rate: {new_charge_rate} successfully set")
                            Messages.client.publish(topic=config["TOPIC_CHARGE_RATE"], payload=new_charge_rate, qos=1)
                    else:
                        logging.warning("Car charging, new rate was NOT successfully set")

            else:    # We don't have enough sun
                if round(Energy.charge_rate_sensor) > config["MIN_CHARGE"]:    # If we are charging at anything greater than min charge
                    # Set charge rate to min charge
                    if Car.set_charge_rate(config["MIN_CHARGE"]):
                        logging.info(f"Car charging, Available Energy Reduced, new rate: {config['MIN_CHARGE']} successfully set")
                        Messages.client.publish(topic=config["TOPIC_CHARGE_RATE"], payload=config["MIN_CHARGE"], qos=1)
                    else:
                        logging.warning("Car charging, Available Energy Reduced, new rate was NOT successfully set")

                else:    # We are already at min charge
                    # Wait configured time before stopping
                    waited_long_enough, stop_charging_time = routines.check_elapsed_time(loop_time, stop_charging_time, config["DELAYED_STOP_TIME"])
                    if waited_long_enough:
                        if Car.stop_charging():
                            logging.info("Car charging, Available Energy Reduced, charging was successfully stopped")
                            car_is_charging = False
                            stop_charging_time = 0
                        else:
                            logging.warning("Car charging, Available Energy Reduced, charging was NOT successfully stopped")
                    else:
                        logging.info(f"Car charging, Available Energy Reduced, charging at min rate, stopping in: {round(config['DELAYED_STOP_TIME'] - (loop_time - stop_charging_time))} seconds")

        else:    # Car isn't charging, should it be?
            if Energy.sufficient_generation(config["MIN_CHARGE"]):    # If we have enough sun to charge
                if round(Energy.charge_rate_sensor) < config["MIN_CHARGE"]:	   # Make sure car isn’t already charging
                    if ((Messages.var_topic_teslamate_charge_limit_soc - Messages.var_topic_teslamate_battery_level) > 1):    # If we are charging at least 1%
                        # Wait configured time before starting
                        waited_long_enough, start_charging_time = routines.check_elapsed_time(loop_time, start_charging_time, config["DELAYED_START_TIME"])
                        if waited_long_enough:
                            wake_states = ["asleep", "suspended"]
                            if Messages.var_topic_teslamate_state in wake_states:    # Only wake car if it's asleep
                                if Car.wake():
                                    logging.info("Car is NOT charging, Energy is Available, car woken successfully")
                                    time.sleep(5)    # Wait until car is awake
                                else:
                                    logging.warning("Car was NOT woken successfully")
                            if Car.start_charging():
                                logging.info("Car Started Charging Successfully")
                                time.sleep(10)    # Wait until charging is fully started
                                if Energy.verify_new_charge_rate(config["MIN_CHARGE"]):
                                    logging.info("Charge Rate is greater than min charge")
                                    car_is_charging = True
                                    start_charging_time = 0
                                    # Optionally we could set a new charge rate here
                            else:
                                logging.warning("Car Charging NOT Started Successfully")
                        else:
                            logging.info(f"Car is NOT charging, Energy is Available, starting in: {round(config['DELAYED_START_TIME'] - (loop_time - start_charging_time))} seconds")
                    else:
                        logging.debug("Attempting to charge with only 1% remaining")

                else:    # Car is already charging, set the flag
                    car_is_charging = True
                    start_charging_time = 0

            else:    # Sun isn't generating enough power to charge
                if prevent_non_solar_charge:    # If true, prevent after-hours charging
                    if round(Energy.charge_rate_sensor) >= config["MIN_CHARGE"]:
                        if Car.stop_charging():  # Stop if it is charging
                            logging.info("Fast poll, Car discovered charging and was stopped successfully")
                        else:
                            logging.warning("Fast poll, Car discovered charging and was NOT stopped successfully")

                if start_charging_time != 0:    # If starting time has already been set
                    # Reset start charging time as sun has dropped below the threshold
                    start_charging_time = 0

    elif charge_delay or prevent_non_solar_charge:
            if car_is_charging:
                if Messages.var_topic_teslamate_battery_level == Messages.var_topic_teslamate_charge_limit_soc:
                    logging.info(f"Completed charge to: {Messages.var_topic_teslamate_charge_limit_soc}% limit, stopping charge")
                Car.set_charge_rate(config["MIN_CHARGE"])    # Set charge rate to min charge, to reset for next time
                car_is_charging = False    # Always reset flag if set, actual charge rate is used to stop

            logging.debug("Slow poll wait, ensure car isn't charging")
            if round(Energy.charge_rate_sensor) >= config["MIN_CHARGE"]:
                if Car.stop_charging():     # Stop if it is charging
                    logging.info("Slow poll, Car discovered charging and was stopped successfully")
                    time.sleep(2)    # Delay to allow stop command to complete
                else:
                    logging.warning("Slow poll, Car discovered charging and was NOT stopped successfully")
                Energy.sample_sensor(timeout=5)    # Force sensor refresh to increase accuracy of subsequent loop
            else:
                # Prevent non_solar_charge or delay, wait condition
                time.sleep(config["SLOW_POLLING"])

    else:    # We are allowing car to charge after sundown
        logging.debug("Slow poll wait, ignoring car charge")
        time.sleep(config["SLOW_POLLING"])

    # Wait configured time before reporting status
    report_is_due, report_time = routines.check_elapsed_time(loop_time, report_time, config["REPORT_DELAY"])
    if report_is_due:
        status = Energy.status_report(charge_tesla, charge_delay, sun_up, car_is_charging, new_sample=True)
        logging.info(f"{status}")
        Messages.client.publish(topic=config["TOPIC_STATUS"], payload=status, qos=1)
        report_time = loop_time    # Reset counter for next loop

    # Control loop delay
    time.sleep(config["FAST_POLLING"])
