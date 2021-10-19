/*
 * Weather Station sender
 * Collects data from Wind sensor (microswitch that triggers every rotation), Wind vane (multiple microswitches that form a potential divider depending on position),
 * tipping bucket rain sensor and BME280 temperature,humidity and pressure sensor.
 * Finally, the battery voltage (12V) is monitored. This module is designed to be powered from a solar powered 12V battery.
 * There are 3 timed cycles:
 *    A LCD data write cycle that writes new, updated weather data to the LCD display every 2 seconds
 *    A Wind gust cycle that updates the fastest wind gust every 250ms
 *    A 10s main loop that collects all weather data and sends to a recieving Raspberry Pi for processing and display.
 *    
 *    For wind reporting, wind gusts are updated every 250ms.
 *    Wind speed is averaged over a 10 minute period using a circular buffer
 *    Direction is also averaged over the same 10 minute period
 *    
 *    For rainfall, a calibrated tipping bucket sensor is moniored for a 24 hour period, reset at midnight. 
 *    A rolling 1 hour buffer gives the rainfall per hour reading.
 *    
 *    Every 10 seconds all data is sent to the Raspberry Pi receiver as 2 packets.
 *    The first packet of 32 bytes has all weather data encoded like this:
 *                                                                   Av. Strength
 *                                                                   | | Gust
 *                                                                   | | | | Direction
 *                                                                   | | | | | | |
 * Message Format: T 9 9 . 9 H 9 9 P 9 9 9 9 R 9 9 9 . 9 r 9 9 . 9 W 9 9 9 9 9 9 9
 *                 e         u     r         a           a         i
 *                 m         m     e         i           i         n
 *                 p         i     s         n           n         d
 *                (C)        d     s        (D)         (H)  
 *                 ---------------------------------------------------------------
 *                 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 2 2 2 2 2 2 2 2 2 2 3 3
 *                 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 *                 
 *    The second packet has the battery voltage             
 *    
 *    The Raspberry Pi receives, decodes and displays all data.
 *    The Raspberry Pi then sends current Unix time as am ACK Payload package.
 *    This Ack payload package allows this sensor to know local time (by the Timezone library) for resetting daily rain bucket and displaying time on the LCD.
 *    The Unix time ACK payload returned is "sanity checked" for a valid range and, if valid, is used to correct an on-board RTC.
 *    Only corrected on startup and then once every day at midnight AND if more than 60 seconds out of sync.


 *    
 */


#include <avr/wdt.h>                                                                        // Watchdog timer
#include <avr/interrupt.h>                                                                  // Interrupts
#include "nRF24L01.h"
#include "RF24.h"
#include <TimeLib.h>
#include <LiquidCrystal.h>
#include <Adafruit_BME280.h>
#include "RTClib.h"
#include <ArduinoSort.h>
#include <Timezone.h>
#include <CircularBuffer.h>

// Sensor Pin Definitions
#define RainPin 2
#define WindSpeedPin A3
#define WindDirectionPin A1
#define BatteryPin A0

// Calibration factors
#define PRESS_CAL 1.005
#define TEMP_CAL 1.04
#define TEMP_OFFSET 0.00
#define HUMID_CAL 1.01
#define HUMID_OFFSET 0.00
#define WIND_CAL 1.492
#define BATTERY_CAL 63.74
#define RAIN 0.2794

// Loop timers
#define MAIN_LOOP_TIME 10000.0
#define LCD_UPDATE_TIME 2000.0
#define WIND_GUST_LOOP_TIME 500.0


// Initialize RainHourBuffer
CircularBuffer<unsigned long,60> RainHourBuffer;      // 1 element per 0.3mm of rain
                                                      // Any element older than 1 hour is popped
                                                      // A full buffer would be 18mm rain per hour

// Initialise WindBuffers
CircularBuffer<byte,60> WindSpeedBuffer;              // 10 Minute buffer
CircularBuffer<byte,60> WindGustBuffer;               // 10 Minute buffer
CircularBuffer<int,60> WindDirectionBuffer;           // 10 Minute buffer


// Initialize Temp sensor, Radio, LCD and RTC
Adafruit_BME280 bme;
RF24 radio(9,10);
LiquidCrystal lcd(3, 4, 5, 6, 7, 8);
RTC_DS3231 rtc;

//Time and Timezone variables
TimeChangeRule myDST = {"BST", Last, Sun, Mar, 2, +60};   //British Summer Time
TimeChangeRule mySTD = {"GMT", Last, Sun, Oct, 2, 0};     //GMT
Timezone myTZ(myDST, mySTD);
TimeChangeRule *tcr;        //pointer to the time change rule, use to get TZ abbrev
DateTime RTC_now;
time_t LocalTime;
time_t LocalServerTime;


// Radio Write pipe address - read pipe not needed since we use AutoAck function to get UnixTime
const uint64_t WritePipe = 0x544d52687CLL;

// Initialize various strings
char PayloadString[] = "T00.0H00P0000R000.0r00.9W0000000";
char AckPayload[32];                // Returned Unix time from Pi
char DateTimeString[17];            // For display on LCD
byte BottomLineDataCycle;           // Cycling weather information counter on Bottom line of LCD


// Rain variables
float RainBucket;                   // Daily Rain Bucket - empties at midnight
float RainPerHour;                  // Rolling rain per hour
byte RainHourBufferToShift;         // Number of RainHourBuffer entries to shift that are greater than 1 hour ago

// Rain Interrupt variables
volatile unsigned long LastRainMillis;       // For rain IRQ de-bounce
volatile bool RainDetected;                  // Triggered by Rain IRQ


// Variable used to check for day rollover - to empty daily rain bucket
byte LastDay;

// WindSpeed sensor interrupt counter
volatile int WindSpeedInterruptCounter;
volatile int WindGustInterruptCounter;
volatile unsigned long LastWindSpeedInterrupt;

// Wind Direction values
float WindDirectionVoltage[] = {3.84,1.98,2.25,0.41,0.45,0.32,0.90,0.62,1.40,1.19,3.08,2.93,4.62,4.04,4.33,3.43};
int WindDirectionDegrees[] = {0,22,45,67,90,112,135,157,180,202,225,247,270,292,315,337};

// Wind variables
byte WindSpeed;                      // Average over a rolling 10 minute cycle
int WindDirection;                  // Average over a rolling 10 minute cycle
byte WindDirIndex;                   // Index value of Wind Direction voltage array value
byte WindGust;                       // Peak value over a rolling 10 minute cycle
byte ThisWindGust;                   // Maximum wind gust for every 250ms wind gust cycle
byte LCD_WindSpeed;                  // For display on LCD only (LCD display is asynchronous WRT the windspeed average calculation
byte LCD_WindGust;                   // For display on LCD only (LCD display is asynchronous WRT the wind gust peak detection

float CorrectedTemperature;         // 3 readings are taken and we take the median value and multiply by an empirical correction value
float CorrectedHumidity;            // 3 readings are taken and we take the median value and multiply by an empirical correction value

// Loop timing variables
unsigned long NextMainCycle;
unsigned long NextLCDCycle;
unsigned long NextWindGustCycle;
unsigned long LoopMillis;

// Time check variables
boolean LastTransmit;
// MaxUnixTiime and MinUnixTime used for validity check on transmitted time data from RaspbBerry Pi  
long MaxUnixTime = 1924905600; // December 31st 2030
long MinUnixTime = 1569888000; // October 1st 2019
long ReturnUnixTime;
bool TimeValid;               //Indicates return payload time stamp from Raspberry Pi is valid.

// Do we have an RTC?
boolean RTC = true;

// BME280 Sensor Found?
boolean SensorFound;

boolean VoltageSent = true;                // Status sent flag, we send just once after each data send cycle
boolean TimeSynced = false;


float BattValue;

void setup()
{
//    Serial.begin(115200);
//    Serial.println("Weather Station");
    ThisWindGust = 99;                        // Used as marker in Thingspeak to indicate Arduino reset event
    wdt_enable(WDTO_8S);                      // Enable Watchdog timer   
    SensorFound = false;
    lcd.begin(16, 2);
    lcd.setCursor(0,0);
    lcd.print("Weather Station.");
    lcd.setCursor(0,1);
    lcd.print("  Version 1.0   ");


  // Setup and configure rf radio
    radio.begin();
    radio.setAutoAck(true);
    radio.enableDynamicPayloads(); 
    radio.enableAckPayload();         
    radio.setRetries(10,5);
    radio.setPayloadSize(32);
    radio.setDataRate(RF24_250KBPS);            // Lowest bitrate for highest data integrity
    radio.setPALevel(RF24_PA_HIGH);             // Highest power for range 
    radio.openWritingPipe(WritePipe);



// Get initial values for Day and Hour so we can start rain buckets
    DateTime now = rtc.now();
    time_t utc = now.unixtime();
    time_t LocalTime = myTZ.toLocal(utc, &tcr);
    LastDay = day(LocalTime);

    if (! bme.begin(0x76)) 
      {
        lcd.clear();
        lcd.print("No sensor!");
      }
    else SensorFound = true;  

// Show LCD start message for 2 seconds  
    delay(2000);
    lcd.clear();

// Set up Temp/Humidity/Pressure sensor
    if (SensorFound)
      {
      bme.setSampling(Adafruit_BME280::MODE_FORCED,
                  Adafruit_BME280::SAMPLING_X2, // temperature
                  Adafruit_BME280::SAMPLING_X2, // pressure
                  Adafruit_BME280::SAMPLING_X2, // humidity
                  Adafruit_BME280::FILTER_OFF);  
      }

// Start Rainbucket ISR
    pinMode(RainPin, INPUT_PULLUP);
    attachInterrupt (digitalPinToInterrupt(RainPin), RainIRQ, FALLING);
    RainBucket = 0;
    RainPerHour = 0;
    RainDetected = false;

// Start WindSpeed ISR
    pinMode(WindSpeedPin, INPUT_PULLUP);    
    PCICR |= 0b00000010;                      // Enable A0-A5 pin interrupts (Wind sensor is on A3)
    PCMSK1 |= 0b00001000;                     // Enable A3 pin interrupts (Wind Sensor)


}




void loop(void) 
{
  float TemperatureArray[3],HumidityArray[3],PressureArray[3];  // We take the median of 3 readings
  LoopMillis = millis();
  char LCD_Bottom_Line[17];
  char ReadString[10];                                          // Char array to hold converted read back values
  wdt_reset();                                                  // Reset watchdog timer
  float ThisWindSpeed;
  int ThisWindDirection;

  if (LoopMillis > NextWindGustCycle)                           // Capture wind gust every 0.25s
    {
    NextWindGustCycle = LoopMillis + WIND_GUST_LOOP_TIME;       // Calculate next wind gust capture
    ThisWindSpeed = WindGustInterruptCounter*2/WIND_CAL;
    if (ThisWindSpeed > ThisWindGust)
      ThisWindGust = ThisWindSpeed;                             // This captured gust is bigger than any since the last 10 second cycle
    WindGustInterruptCounter = 0;                               // Reset WindGust interrupt for next cycle
    }
      

// Put cycling weather data on LCD Bottom Line
  if (LoopMillis > NextLCDCycle)
    {
    NextLCDCycle = LoopMillis + LCD_UPDATE_TIME;              // Calculate time of next LCD update 
    if (BottomLineDataCycle < 8)
      BottomLineDataCycle++;
    else
      BottomLineDataCycle=0;
         
    lcd.setCursor(0,1);
      
    char LCD_Bottom_Line_Data[17];
    switch (BottomLineDataCycle)
      {
      case 0 : dtostrf(CorrectedTemperature,9,1,LCD_Bottom_Line_Data);
               sprintf(LCD_Bottom_Line,"Temp:%s C",LCD_Bottom_Line_Data);
      break;  
      case 1 : dtostrf(CorrectedHumidity,8,1,LCD_Bottom_Line_Data);
               sprintf(LCD_Bottom_Line,"Humid:%s %",LCD_Bottom_Line_Data);
      break;  
      case 2 : dtostrf((PressureArray[1]/100 * PRESS_CAL),6,1,LCD_Bottom_Line_Data);
               sprintf(LCD_Bottom_Line,"Press:%s hPa",LCD_Bottom_Line_Data);
      break;  
      case 3 : dtostrf(RainBucket,8,1,LCD_Bottom_Line_Data);
               sprintf(LCD_Bottom_Line,"Rain:%s mm",LCD_Bottom_Line_Data);
      break;  
      case 4 : dtostrf(RainPerHour,6,1,LCD_Bottom_Line_Data);
               sprintf(LCD_Bottom_Line,"Rain/H:%s mm",LCD_Bottom_Line_Data);
      break;  
      case 5 : sprintf(LCD_Bottom_Line,"Wind:%3d mph    ",LCD_WindSpeed);
      break;  
      case 6 : sprintf(LCD_Bottom_Line,"Gust:%3d mph    ",LCD_WindGust);
      break;
      case 7 : sprintf(LCD_Bottom_Line,"Dir:%3d         ",WindDirection);
      break; 
      case 8 : if (LastTransmit)
                {
                if (TimeValid)  
                  sprintf(LCD_Bottom_Line,"Transmit OK (T) ");
                else  
                  sprintf(LCD_Bottom_Line,"Transmit OK (F) ");
                }
               else
                sprintf(LCD_Bottom_Line,"Transmit FAIL   "); 
      break; 
      }
    lcd.print(LCD_Bottom_Line);          
    }


// Collect all weather data every 10 seconds
  if (LoopMillis > NextMainCycle)
    {
    PrintDateTime(LocalTime);
    VoltageSent = false;                                          // We will send Battery voltage once after sending weather data
    NextMainCycle = millis()+ MAIN_LOOP_TIME;                     // calculate time of next update
    RainPerHour=0;                                                // Initialize Rain Per Hour indicator
    WindSpeed=0;                                                  // Initialise wind speed for average calculation
    WindDirection=0;                                              // Initialise Wind direction for average calculation
    WindGust=0;
    ThisWindSpeed=WindSpeedInterruptCounter/10*WIND_CAL;
    WindSpeedInterruptCounter=0;
    WindSpeedBuffer.push(ThisWindSpeed);                          // Push one record into Wind Speed buffer
    WindDirIndex = GetWindDirection();
    WindDirectionBuffer.push(WindDirectionDegrees[WindDirIndex]); // Push one record into Wind Direction buffer
    WindGustBuffer.push(ThisWindGust);                            // Push the largest wind gust into wind gust buffer
    ThisWindGust=0;


// Rain    
    if (RainDetected)                                             // Rain IRQ triggered
      {
      RainBucket+=RAIN;                                           // Increase daily rain counter
      RainHourBuffer.push(LoopMillis);                            // Push one record into hourly buffer
      RainDetected=false;                                         // Reset rain IRQ trigger
      }  

    if (!RainHourBuffer.isEmpty())                                  // If any rain in hourly rain buffer
      {
      RainHourBufferToShift=0;                                      // Initialize counter of records over 1 hour
      for (int BufferLoop = 0; BufferLoop < RainHourBuffer.size(); BufferLoop++)
        {
        if (millis() < (RainHourBuffer[BufferLoop] + 3600000))
          RainPerHour+=RAIN;                                      // For every record in buffer younger than 1 hour, add one rain quantity
        else
          RainHourBufferToShift+=1;                                 // For every record older than 1 hour mark that it needs deleting (shifting)
        }
      for (int PopLoop = 0; PopLoop < RainHourBufferToShift; PopLoop++)
        RainHourBuffer.shift();                                     // Lose any record older than 1 hour
      }  

//Reset the day rain bucket if we have changed day
    if ((day(LocalTime) != LastDay))
      {
      RainBucket = 0;
      LastDay = day(LocalTime);
      TimeSynced = false;                                         // Do an internet time sync at midnight every day.
      }


//Temperature, Humidity, Pressure
    if (SensorFound)
      {
      for (int ReadCycle = 0; ReadCycle < 3; ReadCycle ++)
        {
        bme.takeForcedMeasurement();                            // Take one Temp/Humid/Pressure measurement and then go back to sleep
        TemperatureArray[ReadCycle] = bme.readTemperature();    // Get temperature in C
        HumidityArray[ReadCycle] = bme.readHumidity();          // Get humidity
        PressureArray[ReadCycle] = bme.readPressure();          // Get Pressure
        }        	
      }
    // Sort the three values so we can take the middle one  
    sortArray(TemperatureArray, 3); 
    sortArray(HumidityArray, 3); 
    sortArray(PressureArray, 3);

// Work out all the values to send and format Payload string
    PayloadString[0] = 'T';                                     // Set Temperature marker in Payload string

    CorrectedTemperature = (TemperatureArray[1]*TEMP_CAL) + TEMP_OFFSET;  // Correction derived empirically
    dtostrf(CorrectedTemperature,4,1,ReadString);               // Convert to string, 1 decimal place accuracy for sending to Pi

    // Copy Temperature to array to send to Pi 
    if (SensorFound) 
      for (int i = 1; i < 5; i++) PayloadString[i] = ReadString[i-1];
    
    PayloadString[5] = 'H';                                     // Set Humidity marker in Payload string
    CorrectedHumidity = (HumidityArray[1]*HUMID_CAL) + HUMID_OFFSET;       // Correction derived empirically
    dtostrf(constrain (CorrectedHumidity,1,99),2,0,ReadString); // Convert to string, 0 decimal place accuracy for sending to Pi

    // Copy Humidity to array to send to Pi
    if (SensorFound)      
      for (int i = 6; i < 8; i++) PayloadString[i] = ReadString[i-6];
    
    PayloadString[8] = 'P';                                     // Set Pressure marker in Payload string
    dtostrf((PressureArray[1]/100 * PRESS_CAL),4,0,ReadString); // Convert to string, 0 decimal place accuracy for sending to Pi
    if (ReadString[0]==' ') ReadString[0]='0';

    // Copy Pressure to array to send to Pi
    if (SensorFound)        
      for (int i = 9; i < 13; i++) PayloadString[i] = ReadString[i-9];

    PayloadString[13] = 'R';                                    // Set Dail Rain marker in Payload string
    dtostrf(RainBucket,5,1,ReadString);
    if (ReadString[0]==' ') ReadString[0]='0';
    if (ReadString[1]==' ') ReadString[1]='0';
    for (int i = 14; i <19; i++) PayloadString[i] = ReadString[i-14]; 

    PayloadString[19] = 'r';                                    // Set Rain per Hour marker in Payload string
    dtostrf(RainPerHour,4,1,ReadString);
    if (ReadString[0]==' ') ReadString[0]='0';
    for (int i = 20; i <24; i++) PayloadString[i] = ReadString[i-20];

    PayloadString[24]='W';                                      // Set Wind marker in Payload string
    for (int WindLoop = 0; WindLoop < WindSpeedBuffer.size(); WindLoop++)
        WindSpeed+=WindSpeedBuffer[WindLoop];
    WindSpeed = WindSpeed / WindSpeedBuffer.size();
    

    for (int WindLoop = 0; WindLoop <WindGustBuffer.size(); WindLoop++)
        {
        if (WindGustBuffer[WindLoop] > WindGust)
          WindGust = WindGustBuffer[WindLoop];
        }  

    WindDirection = AverageWindDirection(WindDirectionBuffer.size());

    sprintf(ReadString,"%02d",WindSpeed);
    for (int i = 25; i < 27; i++) PayloadString[i] = ReadString[i-25];
    sprintf(ReadString,"%02d",WindGust);
    for (int i = 27; i < 29; i++) PayloadString[i] = ReadString[i-27];
    sprintf(ReadString,"%03d",WindDirection);
    for (int i = 29; i < 32; i++) PayloadString[i] = ReadString[i-29];
    LCD_WindSpeed=WindSpeed;
    LCD_WindGust=WindGust;
    WindSpeed=0;
    WindGust=0;                    

    SendToRadio(true);
    }
  else if (VoltageSent == false) // Send status just once after every data send
    {  
      BattValue= analogRead(BatteryPin) / BATTERY_CAL;
      PayloadString[0] = 'S';     
      dtostrf(BattValue,4,2,ReadString);
      for (int i = 1; i <6; i++) PayloadString[i] = ReadString[i-1];
      SendToRadio(false);
      VoltageSent = true;
    }
}

int AverageWindDirection(int BufferSize)
  {
  float SinTotal=0;
  float CosTotal=0;
  float Radians=0;
  float DirectionFloat=0;
  int Direction=0; 
  for (int WindLoop = 0; WindLoop < BufferSize; WindLoop++)
    {
    Radians = WindDirectionBuffer[WindLoop] * 71 / 4068.0;
    SinTotal = SinTotal + sin(Radians);
    CosTotal = CosTotal + cos(Radians);    
    }
  SinTotal = SinTotal / BufferSize;  
  CosTotal = CosTotal / BufferSize;
  Radians = atan2(SinTotal,CosTotal);  // This is the average in Radians
  DirectionFloat = (Radians * 4068 / 71.0)+360;
  Direction=DirectionFloat;
  return (Direction%360);
  }

void SendToRadio(bool SyncPayload)
  {
  int ReturnPayloadLength;
  lcd.setCursor(5,1);
  if (radio.write(PayloadString, 32)) 
    LastTransmit=true;
  else
    LastTransmit=false;
    
  if (radio.isAckPayloadAvailable())
    {
    ReturnPayloadLength = radio.getDynamicPayloadSize();
    radio.read(&AckPayload, ReturnPayloadLength);
    AckPayload[ReturnPayloadLength]=0;
    ReturnUnixTime = atol(AckPayload);

    // Only Sync RTC and set TimeValid IF we are in a transmit weather data cycle (rather than battery voltage) AND  Retrun Unix time is in a sensible range AND we get two valid UnixTimes in sequence.
    if (SyncPayload)
      {
      if ((ReturnUnixTime>MinUnixTime) && (ReturnUnixTime<MaxUnixTime))
        {
        SyncToRTC(ReturnUnixTime);
        TimeValid=true;           
        }
      else
        TimeValid=false;  
      }
    }
  }

ISR(PCINT1_vect)                                                                      // WindSpeed Sensor interrupt
{
  if (millis() - LastWindSpeedInterrupt > 10)                                         // Once every 10ms would be 150MPH
    {
    WindSpeedInterruptCounter++;
    WindGustInterruptCounter++;
    LastWindSpeedInterrupt = millis();  
    }
}

int GetWindDirection()
{
  float WindDirectionValue;
  int NearestIndex = 0;
  WindDirectionValue = analogRead(WindDirectionPin)/1023.0*5.0;
  float Difference=fabs(WindDirectionVoltage[0] - WindDirectionValue);
  for (int w = 1; w < 16; w++)
    {
    if (fabs(WindDirectionVoltage[w] - WindDirectionValue) < Difference)
      {
        NearestIndex = w;
        Difference = fabs(WindDirectionVoltage[w] - WindDirectionValue);
      } 
    }
  return NearestIndex; 
}


void RainIRQ()
  {
    
   if((millis()-LastRainMillis) > 500) // Debounce
      {
      RainDetected = true;  
      LastRainMillis=millis();
      }
  }

void SyncToRTC(time_t UnixTime)
  {
    time_t utc;
    char buf1[20];
    if (RTC == true)
      {
      DateTime RTC_now = rtc.now();
      utc = RTC_now.unixtime();
      }
    else  
      utc = now();
    LocalTime = myTZ.toLocal(utc, &tcr);
    LocalServerTime = myTZ.toLocal(UnixTime, &tcr);
    long TimeDiff = utc-UnixTime;
 
     if ((abs(TimeDiff) > 60) && (!TimeSynced))
    	{
    	if (RTC == true) rtc.adjust(UnixTime);
      else setTime(UnixTime);
      TimeSynced = true;
    	}   
  }

void PrintDateTime(time_t t)
{
    sprintf(DateTimeString, "%.2d:%.2d %.2d/%.2d/%d",
        hour(t), minute(t), day(t), month(t), year(t));
    if (SensorFound)
      { 
      lcd.setCursor(0,0);
      lcd.print(DateTimeString);
      }

}
