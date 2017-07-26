# LoggerBIT Firmware
Firmware to create a data logger for BITalino (r)evolution based on the OpenLog by SparkFun

## Programming the OpenLog with the LoggerBIT firmware
Loading the LoggerBIT firmware onto the OpenLog is the first thing to do. This process **must** be done **without making any physical changes** to the OpenLog board that is currently shipped by SparkFun. 

1. Download the [Arduino IDE version 1.6.5](https://www.arduino.cc/en/Main/OldSoftwareReleases), a verified known good version.
2. Download the [LoggerBIT firmware](https://github.com/BITalinoWorld/firmware-loggerbit/blob/master/LoggerBIT_BIN.ino).
3. Download the required libraries:
   * Bill Greiman's [SerialPort library](https://github.com/greiman/SerialPort)
   * Bill Greiman's [SdFat library](https://github.com/greiman/SdFat)
4. Install the libraries into Arduino. Check [here](https://www.arduino.cc/en/Guide/Libraries) for more detailed instructions on how to do it.
5. Modify the **SerialPort.h** file found in the **\Arduino\Libraries\SerialPort** directory. Change `BUFFERED_TX` to `0` and `ENABLE_RX_ERROR_CHECKING` to `0`.
6. Connect the OpenLog to the computer via an FTDI board. Check [here](https://learn.sparkfun.com/tutorials/openlog-hookup-guide#hardware-hookup) for more detailed instructions on how to make the connection between the two boards.
7. Open the LoggerBIT sketch with the Arduino IDE, select the **Arduino/Genuino Uno** board setting under **Tools>Board**, and select the proper COM port for the FTDI board under **Tools>Port**.
8. Upload the code and it's done!

## What to change in the OpenLog board for using hardware flow-control
Once the OpenLog is loaded with the LoggerBIT firmware, the board has to be physically adjusted, by including the necessary extra wiring, so the hardware flow-control mechanism can properly function.

You will need:
* A male header with 5 pins (right angle)
 <img src="https://github.com/BITalinoWorld/firmware-loggerbit/blob/master/docs/images/5-way-header.jpg" width="128">

* Thin wire (for the shunt)
* Soldering iron and thin solder

Firstly, **bend the leftmost pin of the header**, so that it stays in a straight horizontal direction instead of the original right angle.

*insert image*

Afterwards, place the header on the pads of OpenLog UART interface (at the bottom), so that the bent pin stays over the **GRN pad**. **Solder each of the 5 remaining pins** with the corresponding pad.

*insert image*

Solder one end of the shunt directly on the **2nd pin from the right, on the top side of the MCU** and the other end to the **header pin that hangs above the GRN pad**. Make sure that there is **no solder touching the GRN pad**, it has to remain not connected.

*insert image*

## How to configure the BITalino acquisition settings

## Recommended microSD cards

## How to use the decoder

### Arguments

The decoder accepts 1 out of 3 arguments:

```
-h, --help              show this help message and exit
-p PATHNAME, --pathname PATHNAME
                        the pathname of the folder to decode
-f FILENAME, --filename FILENAME
                        the filename of the single file to decode
```
One of the arguments -p/--pathname -f/--filename is required.

### How to run the decoder?
The decoder can be executed as a script or treated as a module that can be imported. Below there are examples of how to run it for a single file, for both types of execution.  

* Script
```bash
python decoder.py -f "C:\Users\margarida\logs\LOG00000.BIN"
```

* Module
```c#
import decoder
decoder.main([r'-f C:\Users\margarida\logs\LOG00000.BIN'])
```

## Acknowledgments:
This work was partially supported by the IT – Instituto de Telecomunicações under the grant UID/EEA/50008/2013 "SmartHeart" (https://www.it.pt/Projects/Index/4465).
