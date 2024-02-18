
import os
import math
from time import sleep
from dotenv import load_dotenv
from routines import PowerUsage, TeslaCommands, MqttCallbacks

load_dotenv()
# Load parameters from .env
topic_status = os.getenv("TOPIC_STATUS")
topic_charge_rate = os.getenv("TOPIC_CHARGE_RATE")

# Control loop parameters
SLOW_POLLING = 30       # Charging disabled, control topic check interval (seconds)
SLOW_POLLING_CHK = 5    # Charging disabled, prevent non-solar charge check interval (seconds)
FAST_POLLING = 1        # Charging enabled, update rate (seconds)
MIN_CHARGE = 7          # Slowest allowed charge rate (Amps)

# Initialize classes
Energy = PowerUsage()
Car = TeslaCommands()
Messages = MqttCallbacks()

# Control loop variables
car_is_charging = False
report_due_fast = 0
report_due_slow = 0
report_delay_fast = round((60 / (FAST_POLLING + 1.5)))    # Print a report roughly every minute
report_delay_slow = round((60 / SLOW_POLLING))            # Print a report roughly every minute
start_charging_count = 0
stop_charging_count = 0
while True:
    # Check if we are allowed to charge
    charge_tesla = Messages.calculate_charge_tesla()
    prevent_non_solar_charge = Messages.var_topic_prevent_non_solar_charge
    print("New command, charge: " + str(charge_tesla))

    if not charge_tesla:
        for poll in range(0, SLOW_POLLING, SLOW_POLLING_CHK):   # While waiting ensure that the car isn't charging
            if prevent_non_solar_charge:
                print("Sample, wait")
                Energy.sample_sensor()
                if round(Energy.charge_rate_sensor) >= MIN_CHARGE:
                    Car.stop_charging()     # Stop if it is charging
            sleep(SLOW_POLLING_CHK)
        if report_due_slow >= report_delay_slow:
            status = Energy.status_report(charge_tesla, car_is_charging, new_sample=True)
            print(status)
            Messages.client.publish(topic=topic_status, payload=status, qos=1)
            report_due_slow = 0
        report_due_slow += 1

    if charge_tesla:    # If we are allowed to charge
        if car_is_charging:    # Is the car currently charging?
            if Energy.sufficient_generation(MIN_CHARGE):
                # Reset stop counter
                stop_charging_count = 0
                # Calculate new charge rate
                # Use math.floor() on calculate_charge_rate to ensure we are always just "under" the available PV generation capacity
                # Use round() on charge_rate_sensor to prevent constant requests when on the edge of a value
                new_charge_rate = math.floor(Energy.calculate_charge_rate(new_sample=False))
                print("Calculated charge rate: ", new_charge_rate)
                print("Current rate: ", round(Energy.charge_rate_sensor))
                if new_charge_rate != round(Energy.charge_rate_sensor):
                    # Set new charge rate
                    if Car.set_charge_rate(new_charge_rate):
                        if Energy.verify_new_charge_rate(new_charge_rate):
                            print("New charge rate confirmed: ", new_charge_rate)
                            Messages.client.publish(topic=topic_charge_rate, payload=new_charge_rate, qos=1)

            else:    # We don't have enough sun
                if round(Energy.charge_rate_sensor) > MIN_CHARGE:    # If we are charging at anything greater than min charge
                    # Set charge rate to min charge
                    if Car.set_charge_rate(MIN_CHARGE):
                        if Energy.verify_new_charge_rate(MIN_CHARGE):
                            print("New charge rate confirmed: ", MIN_CHARGE)
                            Messages.client.publish(topic=topic_charge_rate, payload=MIN_CHARGE, qos=1)
                else:    # We are already at min charge, begin stopping sequence
                    stop_charging_count += 1
                    print("Do we need to stop? ", stop_charging_count)
                    if stop_charging_count >= 30:
                        print("Need to stop charging")
                        if Car.stop_charging():
                            car_is_charging = False
                            stop_charging_count = 0

        else:    # Car isn't charging, should it be?
            if Energy.sufficient_generation(MIN_CHARGE):    # If we have enough sun to charge
                if round(Energy.charge_rate_sensor) < MIN_CHARGE:	   # Make sure car isn’t already charging
                    start_charging_count += 1
                    print("Do we start? ", start_charging_count)
                    if start_charging_count >= 5:
                        print("Waking car")
                        if Car.wake():
                            sleep(5)    # Wait until car is awake
                            print("Start charging")
                            if Car.start_charging():
                                sleep(10)    # Wait until charging is fully started
                                if Energy.verify_new_charge_rate(MIN_CHARGE):
                                    car_is_charging = True
                                    start_charging_count = 0
                                    # Optionally we could set a new charge rate here
                else:    # Car is already charging, set the flag
                    car_is_charging = True
                    start_charging_count = 0

            else:    # Sun isn't generating enough power to charge
                if prevent_non_solar_charge:    # If true, prevent after-hours charging
                    Energy.sample_sensor()
                    if round(Energy.charge_rate_sensor) >= MIN_CHARGE:
                        Car.stop_charging()  # Stop if it is charging

    else:    # We aren't allowed to charge
        if car_is_charging:
            print("Need to stop charging")
            Car.set_charge_rate(MIN_CHARGE)    # Set charge rate to min charge, to reset for next time
            Car.stop_charging()    # Command will fail if charging has already stopped
            car_is_charging = False    # Clear the flag even if it fails

    if report_due_fast >= report_delay_fast:
        status = Energy.status_report(charge_tesla, car_is_charging, new_sample=True)
        print(status)
        Messages.client.publish(topic=topic_status, payload=status, qos=1)
        report_due_fast = 0
    report_due_fast += 1

    # Main loop delay
    sleep(FAST_POLLING)
