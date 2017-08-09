/*
 2017
 Margarida Reis & Hugo Silva
 Técnico Lisboa
 IT - Instituto de Telecomunicações

 Made in Portugal

 Acknowledgments: This work was partially supported by the IT – Instituto de Telecomunicações
 under the grant UID/EEA/50008/2013 "SmartHeart" (https://www.it.pt/Projects/Index/4465).

 OpenLog hardware and firmware are released under the Creative Commons Share Alike v3.0 license
 http://creativecommons.org/licenses/by-sa/3.0/
 Feel free to use, distribute, and sell varients of OpenLog. All we ask is that you include attribution of 'Based on OpenLog by SparkFun'

 OpenLog is based on the work of Bill Greiman and sdfatlib: https://github.com/greiman/SdFat-beta

 This version has the command line interface and config file stripped out in order to simplify the overall
 program and increase the receive buffer (RAM)

 The only option is the interface baud rate and it has to be set in code, compiled, and loaded onto OpenLog. To
 see how to do this please refer to https://github.com/sparkfun/OpenLog/wiki/Flashing-Firmware

 This firmware was based on the original OpenLog Minimal firmware, developed by Nathan Seidle from SparkFun Electronics

 */

#define __PROG_TYPES_COMPAT__ // needed to get SerialPort.h to work in Arduino 1.6.x

#include <SPI.h>
#include <SdFat.h> // we do not use the built-in SD.h file because it calls Serial.print
#include <FreeStack.h> // allows us to print the available stack/RAM size

#include <avr/sleep.h> // needed for sleep_mode
#include <avr/power.h> // needed for powering down peripherals such as the ADC/TWI and Timers

#include <math.h>

#include <SerialPort.h>
// port 0, 1024 byte RX buffer, 0 byte TX buffer
SerialPort<0, 1024, 0> NewSerial;

// DEBUG turns on (1) or off (0) a bunch of verbose debug statements. normally use (0)
#define DEBUG  0

#define SD_CHIP_SELECT 10 // on OpenLog this is pin 10

// digital pin numbers
const byte stat = 5;
const byte cts = 6;

// blinking LED error codes
#define ERROR_SD_INIT     3
#define ERROR_NEW_BAUD    5
#define ERROR_CARD_INIT   6

#define ERROR_VOLUME_INIT 7
#define ERROR_ROOT_INIT   8
#define ERROR_FILE_OPEN   9

#define MAX_LOG "LOG00000.BIN"
#define MAX_LOG_LENGTH  (strlen(MAX_LOG) + 1) // length of text found in log file. strlen ignores \0 so we have to add it back

#define CFG_FILENAME "config.txt" // name of the JSON file that contains the unit settings (only standard 8.3 file names are supported)
#define MAX_CFG "1000,simulated,123456,00,00\0"
// = sample all channels at the maximum sampling rate while in simulated mode
#define MAX_CFG_LENGTH (strlen(MAX_CFG) + 1) // length of text found in config file. strlen ignores \0 so we have to add it back
#define MAX_SET_LENGTH  10 // max length of a setting is 10, the mode setting = 'simulated' plus '\0'

SdFat sd;
SdFile workingFile;

// variables related to the configurations from the JSON file
uint8_t no_channels = 4; // by default log 4 channels
uint8_t sd_logging = 1; // by default the system samples and logs 4 channels @ 1 kHz, while in live mode
boolean i1 = 0, i2 = 0;
byte digital_cmd = 0x00;

// handle errors by printing the error type and blinking LEDs in certain way
// the function will never exit - it loops forever inside blinkError
void systemError(byte errorType) {
  NewSerial.print(F("Error "));
  switch (errorType) {
    case ERROR_CARD_INIT:
      NewSerial.print(F("card.init"));
      blinkError(ERROR_SD_INIT);
      break;
    case ERROR_VOLUME_INIT:
      NewSerial.print(F("volume.init"));
      blinkError(ERROR_SD_INIT);
      break;
    case ERROR_ROOT_INIT:
      NewSerial.print(F("root.init"));
      blinkError(ERROR_SD_INIT);
      break;
    case ERROR_FILE_OPEN:
      NewSerial.print(F("file.open"));
      blinkError(ERROR_SD_INIT);
      break;
  }
}

void setup(void) {
  pinMode(stat, OUTPUT);

  // set state for the CTS pin
  pinMode(cts, OUTPUT);
  digitalWrite(cts, LOW);

  // power down various bits of hardware to lower power usage
  set_sleep_mode(SLEEP_MODE_IDLE);
  sleep_enable();

  // shut off TWI, Timer2, Timer1, ADC
  ADCSRA &= ~(1 << ADEN); // disable ADC
  ACSR = (1 << ACD); // disable the analog comparator
  DIDR0 = 0x3F; // disable digital input buffers on all ADC0-ADC5 pins
  DIDR1 = (1 << AIN1D) | (1 << AIN0D); // disable digital input buffer on AIN1/0

  power_twi_disable();
  power_timer1_disable();
  power_timer2_disable();
  power_adc_disable();

  // setup UART
  long uart_speed = 115200;
  NewSerial.begin(uart_speed);

  // this is done so we can "drop" the AT command in case it is sent by BITalino, which happens only after at least 750ms
  _delay_ms(2000);
  NewSerial.flushRx();

  NewSerial.write((byte)0x00); // enter immediately in idle mode (BITalino must be in idle mode in order to send a live mode command)

  // setup SD & FAT
  if (!sd.begin(SD_CHIP_SELECT, SPI_FULL_SPEED)) systemError(ERROR_CARD_INIT);

  // open the log file that getFileName() returns, responsible for checking what the file name should be
  openFile(getFileName());

  // check if there is a .TXT file in the SD card containing the configuration details for BITalino
  readConfigFile();

#if DEBUG
  NewSerial.print(F("\n\nFreeStack: "));
  NewSerial.println(FreeStack());
#endif
}

void loop(void) {
  appendFile();
}

char* getFileName(void) {
  char* testFileName = (char *)malloc(MAX_LOG_LENGTH);

  if (!sd.chdir()) systemError(ERROR_ROOT_INIT); // open the root directory

  // test all numbers starting from 0 (up until 65535)
  for (int testFileNumber = 0; testFileNumber < 65536; testFileNumber++) {
    sprintf(testFileName, "LOG%05d.BIN", testFileNumber);
    if (!sd.exists(testFileName)) { // there is no file with that file number: use it!
      break;
    }
    else { // there is a file with that file number: check to see if it's empty
      SdFile newFile;
      if (newFile.open(testFileName, O_READ)) {
        if (newFile.fileSize() == 0) { // the file exists but is in fact empty: use it!
          newFile.close(); // close the existing empty file we just opened
          break;
        }
        newFile.close(); // the file wasn't empty, just close it and try the next number
      }
    }
  }

  return testFileName;
}

void openFile(char* fileName) {
  if (!sd.chdir()) systemError(ERROR_ROOT_INIT); // open the root directory

  // O_CREAT - create the file if it does not exist
  // O_APPEND - seek to the end of the file prior to each write
  // O_WRITE - open for write
  if (!workingFile.open(fileName, O_CREAT | O_APPEND | O_WRITE)) systemError(ERROR_FILE_OPEN);

  if (workingFile.fileSize() == 0) {
    // this is a trick to make sure first cluster is allocated - found in Bill's example/beta code
    workingFile.rewind();
    workingFile.sync();
  }

  return;
}

void readConfigFile(void) {
  SdFile configFile;

  uint16_t binary_header = 0x0000;

  if (!sd.chdir()) systemError(ERROR_ROOT_INIT); // open the root directory

  char configFileName[strlen(CFG_FILENAME)];
  strcpy_P(configFileName, PSTR(CFG_FILENAME));

  if (!configFile.open(configFileName, O_READ)) {
    configFile.close();
    // if there is no configuration file, then set the default parameters
    // acquire 4 channels (A1-A4) in live mode @ 1 kHz (the sampling rate is the default one)
    NewSerial.write((byte)0x3D);
#if DEBUG
    NewSerial.println();
    NewSerial.println(F("no configuration file found, working with the defaults"));
#endif
    binary_header = 0x18F0;
    // before we start logging, store the user-defined CSV configurations at the beginning of the log file (binary header)
    toggleLED(stat);
    workingFile.write(binary_header >> 8);
    workingFile.write(binary_header);
    workingFile.write(0x0A); // ensure retro-compatibility, write the '\0'
    workingFile.println();
    return;
  }

  // if there is a configuration file then load settings from file
  char settingsArray[MAX_CFG_LENGTH];
  configFile.fgets(settingsArray, sizeof(settingsArray));
  // close the configuration file
  configFile.close();

#if DEBUG
  for (int i = 0; i < strlen(settingsArray); i++)
    NewSerial.print(settingsArray[i]);
  NewSerial.println();
#endif

  // parse the settings out
  int len = strlen(settingsArray);
  char settingString[MAX_SET_LENGTH];
  char mode[MAX_SET_LENGTH];
  
  byte i = 0, j = 0, settingNumber = 0;
  for (i = 0; i < len; i++) {
    // pick out one setting from the line of text
    for (j = 0; settingsArray[i] != ',' && i < len && j < MAX_SET_LENGTH; ) {
      settingString[j] = settingsArray[i];
      i++;
      j++;
    }
    settingString[j] = '\0'; // terminate the string for array compare

    if (settingNumber == 0) { // sampling rate
      // configure the sampling rate first as BITalino is already in idle mode
      int sampling_rate = atoi(settingString);
      switch (sampling_rate) {
        case 1:
          NewSerial.write((byte)0x03);
          break;
        case 10:
          binary_header |= 0x0800;
          NewSerial.write((byte)0x43);
          break;
        case 100:
          binary_header |= 0x1000;
          NewSerial.write((byte)0x83);
          break;
        case 1000:
          binary_header |= 0x1800;
          NewSerial.write((byte)0xC3);
          break;
        default: // should the user enter an invalid choice, default back to 1 kHz
          binary_header |= 0x1800;
          NewSerial.write((byte)0xC3);
          break;
      }
#if DEBUG
      NewSerial.println();
      NewSerial.print(sampling_rate);
      NewSerial.print(F(" Hz"));
#endif
    }

    else if (settingNumber == 1) { // mode
      strcpy(mode, settingString);
    }

    else if (settingNumber == 2) { // channels 
      // configure the channels to acquire afterwards, meaning BITalino will enter live (or simulated) mode
      no_channels = strlen(settingString);
#if DEBUG
      NewSerial.println();
      NewSerial.print(mode);
      NewSerial.print(F(" mode"));
#endif
#if DEBUG
      NewSerial.println();
      NewSerial.print(no_channels);
      NewSerial.print(F(" channels"));
#endif
      byte state_cmd = 0x00;
      if (no_channels > 6) { // invalid choice, default back to acquire 4 channels
        no_channels = 4;
      }
      if (no_channels == 6) { // acquire all channels
        if ((strchr(mode, 's') - mode) == 0) { // simulated mode
          binary_header |= 0x0400;
          state_cmd = 0xFE;
        }
        else { // live mode (or any other option, should the user enter an invalid choice, default back to live mode)
          state_cmd = 0xFD;
        }
#if DEBUG
        NewSerial.println();
        NewSerial.println(F("all channels"));
#endif
        binary_header |= 0x03F0;
      }
      else { // acquire specific channels
        byte cmd = 0x00;
        if ((strchr(mode, 's') - mode) == 0) { // simulated mode
          binary_header |= 0x0400;
          cmd = 0x02;
        }
        else { // live mode (or any other option, should the user enter an invalid choice, default back to live mode)
          cmd = 0x01;
        }
        for (byte n = 0; n < no_channels; n++) {
          int channel_no = settingString[n]-'0';
          if (channel_no >= 1 && channel_no <= 6) {
            binary_header |= (1 << (channel_no + 3));
            cmd |= (1 << (channel_no + 1));
          }
          else { // there is a channel # that is < 1 or > 6, which is an invalid option, default back to acquire 4 channels
            cmd |= 0x3C;
            break;
          }
        }
        state_cmd = cmd;
      }
      NewSerial.write((byte)state_cmd);
    }

    else if (settingNumber == 3) { // trigger
      // the sampling rate, channels and mode are all configured and BITalino is now sampling
      // next we have to define when the logging actually starts depending on the selected trigger
      if (strlen(settingString) != 2) { // invalid option, default back to [0, 0]
        i1 = 0;
        i2 = 0;
      }
      else {
        i1 = settingString[0]-'0';
        i2 = settingString[1]-'0';
        if (i1 != 0 && i1 != 1) { // digital state different from 0 or 1, invalid option, default back to [0, 0]
          i1 = 0;
          i2 = 0;
        }
        if (i2 != 0 && i2 != 1) { // digital state different from 0 or 1, invalid option, default back to [0, 0]
          i1 = 0;
          i2 = 0;
        }
      }
      if (i1 == 0 && i2 == 0) { // start logging immediately
        sd_logging = 1;
#if DEBUG
        NewSerial.println();
        NewSerial.print(F("log now"));
#endif
      }
      else {
        sd_logging = 0;
#if DEBUG
        NewSerial.println();
        NewSerial.println(i1);
        NewSerial.println(i2);
        NewSerial.print(F("wait to log"));
#endif
      }
      binary_header |= i1 << 3;
      binary_header |= i2 << 2;
    }

    else if (settingNumber == 4) { // digital IO
      boolean o1_init_state = 0, o2_init_state = 0;
      if (strlen(settingString) != 3) { // invalid option, default back to [0, 0]
        // here use '3' for the strlen because of the '\0'
        o1_init_state = 0;
        o2_init_state = 0;
      }
      else {
        o1_init_state = settingString[0]-'0';
        o2_init_state = settingString[1]-'0';
        if (o1_init_state != 0 && o1_init_state != 1) { // digital state different from 0 or 1, invalid option, default back to [0, 0]
          o1_init_state = 0;
          o2_init_state = 0;
        }
        if (o2_init_state != 0 && o2_init_state != 1) { // digital state different from 0 or 1, invalid option, default back to [0, 0]
          o1_init_state = 0;
          o2_init_state = 0;
        }
      }
#if DEBUG
      NewSerial.println();
      NewSerial.println(o1_init_state);
      NewSerial.println(o2_init_state);
#endif
      byte aux_cmd = 0x0F;
      aux_cmd ^= (-o1_init_state ^ aux_cmd) & (1 << 2); // set or clear the bit associated with O1
      aux_cmd ^= (-o2_init_state ^ aux_cmd) & (1 << 3); // set or clear the bit associated with O2
      digital_cmd = 0xB0 | aux_cmd;
      if (sd_logging == 1) { // the system will start logging immediately, set now the state of the digital outputs
        NewSerial.write((byte)digital_cmd);
      }
      binary_header |= o1_init_state << 1;
      binary_header |= o2_init_state;
    }

    else
     // we're done! stop looking for settings
     break;

    settingNumber++;
  }

  // before we start logging, store the user-defined CSV configurations at the beginning of the log file (binary header)
  toggleLED(stat);
  workingFile.write(binary_header >> 8);
  workingFile.write(binary_header);
  workingFile.write(0x0A); // ensure retro-compatibility, write the '\0'
  workingFile.println();

  return; 
}

byte appendFile(void) {
	uint8_t last_read = 0;
	uint8_t byte_counter = 0;
	uint8_t no_bytes = 0;
	if (sd_logging == 0) {
		if (no_channels <= 4)
			no_bytes = int(ceil((12. + 10. * no_channels) / 8.));
		else
			no_bytes = int(ceil((52. + 6. * (no_channels - 4)) / 8.));
	}
  uint8_t i1_init_state = 1, i2_init_state = 1; // both inputs are active-low

  const int LOCAL_BUFF_SIZE = 128; // this is the 2nd buffer, it pulls from the larger Serial buffer as quickly as possible.
  byte buff[LOCAL_BUFF_SIZE];
  byte charsToRecord = 0;
	int charsCount = 0;

  const unsigned int CHAR_COUNT = 8000;

#if DEBUG
  NewSerial.print(F("FreeStack: "));
  NewSerial.println(FreeStack());
#endif

  digitalWrite(stat, HIGH); // turn on indicator LED
  
  if (sd_logging == 0) {
    while (1) {
		  digitalWrite(stat, LOW); // turn off stat LED
		  // fetch a single byte at a time
      // we need to know the exact number of bytes the system receives so we can analyze the digital inputs	  
		  if (NewSerial.available() > 0) {
			  int incomingByte = NewSerial.read();
			  byte_counter++;
			  if (byte_counter == (no_bytes - 1)) { // isolate the byte containing the state of the digital inputs (I1 and I2)
				  incomingByte = (uint8_t)incomingByte;
				  incomingByte = (incomingByte & 0xC0) >> 6;
				  uint8_t i1_cur_state = (incomingByte & 0b10) >> 1; 
				  uint8_t i2_cur_state = (incomingByte & 0b01); 
				  if (i1 == 1 && i2 == 0) { // look for change in input I1 only
					  if (i1_cur_state == !i1_init_state)
						// fetch the last byte with the sequence number + CRC so logging to the SD card is done from the beginning  
            last_read = 1; 
				  }
				  else if (i1 == 0 && i2 == 1) { // look for change in input I2 only
					  if (i2_cur_state == !i2_init_state)
						  last_read = 1;
				  }	
				  else { // look for change in both inputs
					  if ((i1_cur_state == !i1_init_state) && (i2_cur_state == !i2_init_state))
						  last_read = 1;
				  }
			  }
			  if (byte_counter == no_bytes) {
				  byte_counter = 0;
				  if (last_read == 1) {
					  //sd_logging = 1; // initiate logging to the SD card in the next cycle
            NewSerial.write((byte)digital_cmd); // set the state of the digital outputs
            break;
          }
			  }
		  }
	  }
  }
  
  // start recording incoming characters
  while (1) {
  	charsToRecord = NewSerial.read(buff, sizeof(buff));
  	if (charsToRecord > 0) {
      charsCount += charsToRecord;
    	toggleLED(stat); 
    	workingFile.write(buff, charsToRecord);
  	}
  	if (charsCount >= CHAR_COUNT) {
    	digitalWrite(cts, HIGH);
    	_delay_ms(1);
    	workingFile.sync(); // sync the card
    	digitalWrite(cts, LOW);
      charsCount = 0;
  	}
	}

  return (1); // we should never get here!
}

// blinks the status LEDs to indicate a type of error
void blinkError(byte ERROR_TYPE) {
  while (1) {
		for (int x = 0 ; x < ERROR_TYPE ; x++) {
      digitalWrite(stat, HIGH);
      delay(200);
      digitalWrite(stat, LOW);
      delay(200);
    }
    delay(2000);
  }
}

// given a pin, it will toggle it from high to low or vice versa
void toggleLED(byte pinNumber) {
  if (digitalRead(pinNumber)) digitalWrite(pinNumber, LOW);
  else digitalWrite(pinNumber, HIGH);
}
