# PVCharge
PVCharge adjusts charging rate based on generated solar energy


Requirements:
-Tesla vehicle
-TeslaMate: https://github.com/teslamate-org/teslamate
-eGauge solar monitoring: https://www.egauge.net
Optional:
-Home Assistant or other MQTT client to change prevent_non_solar_charge option


PVCharge uses Tesla's Vehicle Command SDK, to communicate with your car over local Bluetooth
https://github.com/teslamotors/vehicle-command

git clone https://github.com/teslamotors/vehicle-command.git

To support Waking over BLE, please apply this fix: https://github.com/teslamotors/vehicle-command/pull/106

Golang support install: https://pimylifeup.com/raspberry-pi-golang/

(Use arm64 for 64bit Pi OS)
wget https://go.dev/dl/go1.22.0.linux-arm64.tar.gz -O go.tar.gz
sudo tar -C /usr/local -xzf go.tar.gz

Add these lines to the bottom of ~/.bashrc
export GOPATH=$HOME/go
export PATH=/usr/local/go/bin:$PATH:$GOPATH/bin
export TESLA_KEY_NAME=pi
export TESLA_VIN=<vehicle VIN>
export TESLA_KEY_FILE=$HOME/.local/share/keyrings/private_key.pem

Source ~/.bashrc

From ~/vehicle-command/cmd/tesla-control
go get
go build
go install
From ~/vehicle-command/cmd/tesla-keygen
go get
go build
go install

Binaries are now located ~/go/bin

Create the directory "keyrings" to hold your private key
mkdir /home/pi/.local/share/keyrings

Setting the key
tesla-keygen -key-file /home/pi/.local/share/keyrings/private_key.pem create > public_key.pem

When in the car, pair with this command:
tesla-control -ble add-key-request public_key.pem owner cloud_key
