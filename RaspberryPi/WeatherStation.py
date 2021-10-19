#!/usr/bin/python3

import math
import threading
from flask import Flask, render_template
import time
import datetime
from RF24 import *
import RPi.GPIO as GPIO
import tkinter as tk
from pandas import DataFrame
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import configparser
import Adafruit_DHT
import urllib
import os
import sys

MyAPI = "6TVY1HJ7Q89CRK66"
irq_gpio_pin = None

# Class for all display functions

class Display():

        def __init__(self, main):
                self.Unit = False					# False = metric, True = Imperial
                self.TempHumidOut_Text = tk.StringVar()
                self.TempHumidOut_Text.set("-")

                self.TempHumidIn_Text = tk.StringVar()
                self.TempHumidIn_Text.set("-")

                self.TempOutMinMax_Text = tk.StringVar()
                self.TempOutMinMax_Text.set("-")

                self.TempInMinMax_Text = tk.StringVar()
                self.TempInMinMax_Text.set("-")

                self.Pressure_Text = tk.StringVar()
                self.Pressure_Text.set("-")

                self.PressureMinMax_Text = tk.StringVar()
                self.PressureMinMax_Text.set("-")

                self.Rainfall_Text = tk.StringVar()
                self.Rainfall_Text.set("-")

                self.RainHour_Text = tk.StringVar()
                self.RainHour_Text.set("-")

                self.CurrentTime = tk.StringVar()
                self.CurrentTime.set("-")

                self.BattLevel_Text = tk.StringVar()
                self.BattLevel_Text.set("--.-V")

                os.chdir(os.path.dirname(__file__))

                self.ThermInPic = tk.PhotoImage(file="ThermHumidIn.gif")
                self.ThermOutPic = tk.PhotoImage(file="ThermHumidOut.gif")
                self.PressurePic = tk.PhotoImage(file="Pressure.gif")
                self.RainPic = tk.PhotoImage(file="RainFall.gif")
                self.Signal5Pic = tk.PhotoImage(file="Signal5.gif")
                self.Signal0Pic = tk.PhotoImage(file="Signal0.gif")
                self.WindPic = tk.PhotoImage(file="WindSpeed.gif")
                self.TempRangePic = tk.PhotoImage(file="TempRange.gif")			# Dummy to set 100 pixel height
                self.OtherRangePic = tk.PhotoImage(file="OtherRange.gif")		# Dummy to set 60 pixel height
                self.BattHighPic = tk.PhotoImage(file="BattHigh.gif")
                self.BattMidPic = tk.PhotoImage(file="BattMid.gif")
                self.BattLowPic = tk.PhotoImage(file="BattLow.gif")
                self.weather = main
                self.weatherframe = tk.Frame(self.weather, bg="black", width=800, height=480, relief=tk.RAISED, padx=2, pady=2, borderwidth=5)
                self.weatherframe.grid(row=0, column=0)
                self.weatherframe.grid_propagate(0)
                self.weatherframe.grid_rowconfigure(1, weight=27)
                self.weatherframe.grid_rowconfigure(2, weight=17)
                self.weatherframe.grid_rowconfigure(3, weight=17)
                self.weatherframe.grid_rowconfigure(4, weight=17)
                self.weatherframe.grid_rowconfigure(5, weight=17)

                self.currentlabel = tk.Label(self.weatherframe, textvariable=self.CurrentTime, bg="black", fg="white", font = "Verdana 12 bold")
                self.currentlabel.grid(row=0, column=0, columnspan=4, sticky="n")

                self.temphumidoutlabel = tk.Label(self.weatherframe, image=self.ThermOutPic, compound=tk.LEFT, bg="black", fg="white", textvariable=self.TempHumidOut_Text, anchor="w", relief=tk.SUNKEN, width=260, borderwidth=5, font = "Verdana 25 bold")
                self.temphumidoutlabel.grid(row=1, column=0, sticky="w")

                self.tempoutrangelabel = tk.Label(self.weatherframe, bg="black", fg="white", width=120, image=self.TempRangePic, compound=tk.RIGHT, textvariable=self.TempOutMinMax_Text, relief=tk.SUNKEN, borderwidth=5, font = "Verdana 16 bold")
                self.tempoutrangelabel.grid(row=1,column=1, sticky="w")

                self.temphumidinlabel = tk.Label(self.weatherframe, image=self.ThermInPic, compound=tk.LEFT, bg="black", fg="white", textvariable=self.TempHumidIn_Text, anchor="w", relief=tk.SUNKEN, borderwidth=5, width = 260, font = "Verdana 25 bold")
                self.temphumidinlabel.grid(row=2, column=0, sticky="w")

                self.tempinrangelabel = tk.Label(self.weatherframe, bg="black", fg="white", width=120, image=self.TempRangePic, compound=tk.LEFT, textvariable=self.TempInMinMax_Text, relief=tk.SUNKEN, borderwidth=5, font = "Verdana 16 bold")
                self.tempinrangelabel.grid(row=2,column=1, sticky="w")

                self.pressurelabel = tk.Label(self.weatherframe, image=self.PressurePic, compound=tk.LEFT, bg="black", fg="white", textvariable=self.Pressure_Text, anchor="w", relief=tk.SUNKEN, borderwidth=5, width = 260, font = "Verdana 20 bold")
                self.pressurelabel.grid(row=3, column=0, sticky="w")

                self.pressurerangelabel = tk.Label(self.weatherframe, bg="black", fg="white", width=120, image=self.OtherRangePic, compound=tk.LEFT, textvariable=self.PressureMinMax_Text, relief=tk.SUNKEN, borderwidth=5, font = "Verdana 16 bold")
                self.pressurerangelabel.grid(row=3,column=1, sticky="w")

                self.rainlabel = tk.Label(self.weatherframe, image=self.RainPic, compound=tk.LEFT, bg="black", fg="white", textvariable=self.Rainfall_Text, anchor="w", relief=tk.SUNKEN, borderwidth=5, width = 260, font = "Verdana 20 bold")
                self.rainlabel.grid(row=4, column=0, sticky="w")

                self.rainhourlabel = tk.Label(self.weatherframe, bg="black", fg="white", width=120, image=self.OtherRangePic, compound=tk.LEFT, textvariable=self.RainHour_Text, relief=tk.SUNKEN, borderwidth=5, font = "Verdana 16 bold")
                self.rainhourlabel.grid(row=4,column=1, sticky="w")

                self.signallabel = tk.Label(self.weatherframe, image=self.Signal0Pic)
                self.signallabel.grid(row=0, column=3, sticky="en")

                self.battlabel = tk.Label(self.weatherframe, image=self.BattHighPic, compound=tk.CENTER, fg="black", textvariable=self.BattLevel_Text, font = "Verdana 12 bold")
                self.battlabel.grid(row=0, column=0, sticky="wn")

                self.windcanvas = tk.Canvas(self.weatherframe, bg="black", width=350, height=280, relief=tk.SUNKEN, borderwidth=5)
                self.windcanvas.grid(row=2,column=2, columnspan=2, rowspan=3)

                self.wind_circle = self.windcanvas.create_oval(60,25,300,265,outline='white', width=5)

                self.coords = self.CalculateWindTriangle(0,180,145)
                self.winddirection = self.windcanvas.create_polygon(self.coords[0], self.coords[1], self.coords[2], self.coords[3], self.coords[4], self.coords[5], width=2, outline = "white", fill="blue")
                self.winddirectiontail = self.windcanvas.create_line(self.coords[6], self.coords[7], self.coords[8], self.coords[9], width= 2, fill="white")
                self.windspeed = self.windcanvas.create_text(180,130,text="0", justify=tk.CENTER, fill="white", font="Verdana 20 bold")
                self.windgust = self.windcanvas.create_text(180,160,text="(0)", justify=tk.CENTER, fill="white", font="Verdana 20 bold")
                self.northtext = self.windcanvas.create_text(180,15,text="N", fill="white", font="Verdana 12 bold")
                self.northeasttext = self.windcanvas.create_text(280,53,text="NE", fill="white", font="Verdana 12 bold")
                self.easttext = self.windcanvas.create_text(310,145,text="E", fill="white", font="Verdana 12 bold")
                self.southeasttext = self.windcanvas.create_text(280,240,text="SE", fill="white", font="Verdana 12 bold")
                self.southtext = self.windcanvas.create_text(180,275,text="S", fill="white", font="Verdana 12 bold")
                self.southwesttext = self.windcanvas.create_text(75,235,text="SW", fill="white", font="Verdana 12 bold")
                self.westtext = self.windcanvas.create_text(48,145,text="W", fill="white", font="Verdana 12 bold")
                self.northwesttext = self.windcanvas.create_text(75,53,text="NW", fill="white", font="Verdana 12 bold")
                self.mph = self.windcanvas.create_text(180,190,text="MPH", fill="white", font="Verdana 12 bold")

                self.temphistorycanvas = tk.Canvas(self.weatherframe, bg="black", width=400, bd=5, height=100)
                self.temphistorycanvas.grid(row=1, column=2, columnspan=2)
                self.weather.bind('<Key>',self.Close)

                self.figure1 = plt.Figure(figsize=(3.8,1.1), dpi=100)
                self.TempPlot = self.figure1.add_subplot(111)
                self.TempPlot.set_facecolor("black")
                self.figure1.patch.set_facecolor("black")
                self.TempPlot.spines['bottom'].set_color('white')
                self.TempPlot.tick_params(axis='x',colors='white')
                self.TempPlot.spines['left'].set_color('white')
                self.TempPlot.tick_params(axis='y',colors='white')

                self.figure1.subplots_adjust(left=0.1,bottom=0.3,right=0.95)
                self.TempHistGraph = FigureCanvasTkAgg(self.figure1, self.temphistorycanvas)
                self.TempHistGraph.get_tk_widget().grid(row=0, column=0)
                self.UpdateDisplay()
                self.UpdateTempHistory()


        def Close(self,event):
                self.weather.destroy()


        def CalculateWindTriangle(self,degrees,CentreXCoord,CentreYCoord):
                TipRadians = math.radians(degrees)					# Convert Triangle Tip angle to Radians
                LeftRadians = math.radians(degrees - 18)				# Convert Triangle Left Tip angle to Radians
                RightRadians = math.radians(degrees + 18)				# Convert Triangle Right Tip angle to Radians
                TipXOffsetFromCentre = math.sin(TipRadians) * 115			# 120 = length of radius, but circle is not true on display so fudge it!
                TipYOffsetFromCentre = math.cos(TipRadians) * 115
                LeftXOffsetFromCentre = math.sin(LeftRadians) * 63			# 63 = length of radius to left/right triangle tip
                LeftYOffsetFromCentre = math.cos(LeftRadians) * 63
                RightXOffsetFromCentre = math.sin(RightRadians) * 63
                RightYOffsetFromCentre = math.cos(RightRadians) * 63
                TipXCoord = CentreXCoord + TipXOffsetFromCentre
                TipYCoord = CentreYCoord - TipYOffsetFromCentre
                LeftXCoord = CentreXCoord + LeftXOffsetFromCentre
                LeftYCoord = CentreYCoord - LeftYOffsetFromCentre
                RightXCoord = CentreXCoord + RightXOffsetFromCentre
                RightYCoord = CentreYCoord - RightYOffsetFromCentre
                TailEndRadians = math.radians((degrees+180)%360)
                TailStartXOffsetFromCentre = math.sin(TailEndRadians) * 63
                TailStartYOffsetFromCentre = math.cos(TailEndRadians) * 63
                TailStartXCoord = CentreXCoord + TailStartXOffsetFromCentre
                TailStartYCoord = CentreYCoord - TailStartYOffsetFromCentre
                TailEndXOffsetFromCentre = math.sin(TailEndRadians) * 115
                TailEndYOffsetFromCentre = math.cos(TailEndRadians) * 115
                TailEndXCoord = CentreXCoord + TailEndXOffsetFromCentre
                TailEndYCoord = CentreYCoord - TailEndYOffsetFromCentre
                return (TipXCoord, TipYCoord, LeftXCoord, LeftYCoord, RightXCoord, RightYCoord, TailStartXCoord, TailStartYCoord, TailEndXCoord, TailEndYCoord)

# Function to update the temperature history chart
        def UpdateTempHistory(self):
                global GTempOutMaxFloat
                global GTempOutMinFloat
                global GITempOutMaxFloat
                global GITempOutMinFloat
                self.DayNow = datetime.datetime.now()
                self.CurrentDOW = self.DayNow.weekday()
                if (self.CurrentDOW == 6):
                        self.CurrentDOW = 0						# If it's Sunday then set the history start to previous Monday
                else:
                        self.CurrentDOW += 1						# Otherwise just set the history start to 6 days ago
                self.DOW = ['Mo','Tu','We','Th','Fr','Sa','Su']				# List of days for display
                self.DOW = self.DOW[self.CurrentDOW:] + self.DOW[:self.CurrentDOW] 	# Rotate according to current day of week
                self.TempPlot.clear()
                if not self.Unit:							# Metric
                        MaxTemp = max(GTempOutMaxFloat[1:7])
                        MaxAxisTemp = MaxTemp + (MaxTemp/100.0*10)
                        MinTemp = min(GTempOutMinFloat[1:7])
                        MinAxisTemp = MinTemp - (MinTemp/100.0*10)
                        self.TempPlot.axis([0,5,MinAxisTemp,MaxAxisTemp])
                        self.TempPlot.plot(GTempOutMaxFloat[1:7], color='r')
                        self.TempPlot.plot(GTempOutMinFloat[1:7], color='b')
                else:									# Imperial
                        MaxTemp = max(GITempOutMaxFloat[1:7])
                        MaxAxisTemp = MaxTemp + (MaxTemp/100.0*10)
                        MinTemp = min(GITempOutMinFloat[1:7])
                        MinAxisTemp = MinTemp - (MinTemp/100.0*10)
                        self.TempPlot.axis([0,5,MinAxisTemp,MaxAxisTemp])
                        self.TempPlot.plot(GITempOutMaxFloat[1:7], color='r')
                        self.TempPlot.plot(GITempOutMinFloat[1:7], color='b')
                self.TempPlot.set_yticks([round(MinTemp,-1),round((MaxTemp-MinTemp)/4,-1),round((MaxTemp-MinTemp)/2,-1),round((MaxTemp-MinTemp)*3/4,-1),round(MaxTemp,-1)])
                self.TempPlot.set_xticks([0,1,2,3,4,5])
                self.TempPlot.set_xticklabels(self.DOW[0:6])				# Show rotated days of week
                self.TempPlot.grid()
                self.TempHistGraph.draw()

# Function which dynamically updates all Text and Image variables
        def UpdateDisplay(self):
                global GTempOutFloat
                global GTempInFloat
                global GHumidOutInt
                global GHumidInInt
                global GPressInt
                global GRainFloat
                global GRainHFloat
                global GTempInMaxFloat
                global GTempInMinFloat
                global GTempOutMaxFloat
                global GTempOutMinFloat
                global GHumidMaxInt
                global GHumidMinInt
                global GPressMaxInt
                global GPressMinInt
                global GITempInMaxFloat
                global GITempInMinFloat
                global GITempOutMaxFloat
                global GITempOutMinFloat
                global GWindSpeedInt
                global GWindGustInt
                global GWindDirInt
                global GPressAvThisHour
                global GPressAvLastHour
                global GBattVoltageFloat

                self.CurrentDT = datetime.datetime.now()
                self.CurrentTime.set("Weather Station\n" + self.CurrentDT.strftime("%d-%m-%Y %H:%M"))
                if not self.Unit:
                        self.TempHumidOut_Text.set(' {:.1f}'.format(GTempOutFloat) + u'\N{DEGREE SIGN}C\n(' + str(GHumidOutInt) + '%)')
                        self.TempHumidIn_Text.set(' {:.1f}'.format(GTempInFloat) + u'\N{DEGREE SIGN}C\n(' + str(GHumidInInt) + '%)')
                        self.TempOutMinMax_Text.set('{:.1f}'.format(GTempOutMaxFloat[0]) + "\n\n" + '{:.1f}'.format(GTempOutMinFloat[0]))
                        self.TempInMinMax_Text.set('{:.1f}'.format(GTempInMaxFloat) + "\n\n" + '{:.1f}'.format(GTempInMinFloat))
                        self.PressureMinMax_Text.set(str(GPressMaxInt) + "\n" + str(GPressMinInt))
                        if (GPressAvThisHour > (GPressAvLastHour+1)):
                                self.Pressure_Text.set(str(GPressInt) + " hPa (+)")
                        elif (GPressAvThisHour < (GPressAvLastHour-1)):
                                self.Pressure_Text.set(str(GPressInt) + " hPa (-)")
                        else:
                                self.Pressure_Text.set(str(GPressInt) + " hPa")

                        self.Rainfall_Text.set('{:.1f}'.format(GRainFloat) + " mm")
                        self.RainHour_Text.set('{:.1f}'.format(GRainHFloat) + "/H")
                else:
                        ITempOutFloat = (GTempOutFloat / 5 * 9) + 32
                        ITempInFloat = (GTempInFloat /5 *9) + 32
                        for index in range(7):
                                GITempOutMaxFloat[index] = ((GTempOutMaxFloat[index] /5 * 9) + 32)
                                GITempOutMinFloat[index] = ((GTempOutMinFloat[index] /5 * 9) + 32)
                        GITempInMaxFloat = (GTempInMaxFloat /5 * 9) + 32
                        GITempInMinFloat = (GTempInMinFloat /5 * 9) + 32
                        IPressFloat = GPressInt * 0.03
                        IPressMaxFloat = GPressMaxInt * 0.03
                        IPressMinFloat = GPressMinInt * 0.03
                        IRainFloat = GRainFloat / 25.4
                        IRainHFloat = GRainHFloat / 25.4
                        self.TempHumidOut_Text.set(' {:.1f}'.format(ITempOutFloat) + u'\N{DEGREE SIGN}F\n(' + str(GHumidOutInt) + '%)')
                        self.TempHumidIn_Text.set(' {:.1f}'.format(ITempInFloat) + u'\N{DEGREE SIGN}F\n(' + str(GHumidInInt) + '%)')
                        self.TempOutMinMax_Text.set(' {:.1f}'.format(GITempOutMaxFloat[0]) + "\n\n" + '{:.1f}'.format(GITempOutMinFloat[0]))
                        self.TempInMinMax_Text.set(' {:.1f}'.format(GITempInMaxFloat) + "\n\n" + '{:.1f}'.format(GITempInMinFloat))
                        if (GPressAvThisHour > (GPressAvLastHour+1)):
                                self.Pressure_Text.set('{:.2f}'.format(IPressFloat) + " inHg (+)")
                        elif (GPressAvThisHour < (GPressAvLastHour-1)):
                                self.Pressure_Text.set('{:.2f}'.format(IPressFloat) + " inHg (-)")
                        else:
                                self.Pressure_Text.set('{:.2f}'.format(IPressFloat) + " inHg")
                        self.PressureMinMax_Text.set('{:.1f}'.format(IPressMaxFloat) + "\n" + '{:.1f}'.format(IPressMinFloat))
                        self.Rainfall_Text.set('{:.1f}'.format(IRainFloat) + " in")
                        self.RainHour_Text.set('{:.1f}'.format(IRainHFloat) + "/H")
                if GBattVoltageFloat > 12.5:
                        self.battlabel.config(image=self.BattHighPic)
                elif GBattVoltageFloat > 11.5:
                        self.battlabel.config(image=self.BattMidPic)
                else:
                        self.battlabel.config(image=self.BattLowPic)
                self.BattLevel_Text.set('{:.1f}'.format(GBattVoltageFloat) + "V")

                self.coords = self.CalculateWindTriangle(((GWindDirInt+180)%360),180,145)
                self.windcanvas.itemconfigure(self.windspeed, text=str(GWindSpeedInt))
                self.windcanvas.itemconfigure(self.windgust, text="("+str(GWindGustInt)+")")
                if (GWindSpeedInt == 0 and GWindGustInt == 0):
                         self.windcanvas.itemconfigure(self.winddirection, outline='black')
                         self.windcanvas.itemconfigure(self.winddirection, fill='black')
                else:
                         self.windcanvas.itemconfigure(self.winddirection, outline='white')
                         self.windcanvas.itemconfigure(self.winddirection, fill='blue')
                self.windcanvas.coords(self.winddirection, self.coords[0], self.coords[1], self.coords[2], self.coords[3], self.coords[4], self.coords[5], self.coords[0], self.coords[1])
                self.windcanvas.coords(self.winddirectiontail, self.coords[6], self.coords[7], self.coords[8], self.coords[9])
                self.weatherframe.update()

# Function to show the signal strength icon
        def UpdateSignal(self,SignalLevel):
                if SignalLevel == 5:
                        self.signallabel.config(image=self.Signal5Pic)
                else:
                        self.signallabel.config(image=self.Signal0Pic)

#------------------------------------------------------------------------------------
# End of Display Class
#------------------------------------------------------------------------------------


# Function to get the history values from disk after a power cycle
def ReadINI():
        global GTempOutMaxFloat
        global GTempOutMinFloat
        config = configparser.ConfigParser()
        config.read('Config.ini')
        for index in range(1,7):
                GTempOutMaxFloat[index] = float(config['TempMax'][str(index)])
                GTempOutMinFloat[index] = float(config['TempMin'][str(index)])

# Function that writes the history values to disk at midnight every day
def WriteINI():
        global GTempOutMaxFloat
        global GTempOutMinFloat
        config = configparser.ConfigParser()
        config['TempMax'] = {}
        config['TempMin'] = {}
        for index in range(1,7):
                config['TempMax'][str(index)] = str(GTempOutMaxFloat[index])
                config['TempMin'][str(index)] = str(GTempOutMinFloat[index])
        with open('Config.ini','w') as configfile:
                config.write(configfile)

def GetInsideTempHumid():
        HumidIn = [0.0,0.0,0.0]
        TempIn = [0.0,0.0,0.0]
        for ReadAttempt in range(3):
                try:
                        HumidIn[ReadAttempt], TempIn[ReadAttempt] = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
                except:
                        HumidIn[ReadAttempt] = 0
                        TempIn[ReadAttempt] = 0
        HumidIn.sort()
        TempIn.sort()
        HumidInFloat = HumidIn[1] * 0.925
        TempInFloat = (TempIn[1] * 1.09) - 1.50
        return HumidInFloat, TempInFloat


# The main Tkinter loop
def Get_Weather_Updates():
        global GTimeoutStart
        global GTempOutFloat
        global GTempInFloat
        global GHumidOutInt
        global GHumidInInt
        global GPressInt
        global GPressMaxInt
        global GPressMinInt
        global GPressAvThisHour
        global GPressAvLastHour
        global GPressLastInt
        global GRainFloat
        global GRainHFloat
        global GTempOutMaxFloat
        global GTempOutMinFloat
        global GTempInMaxFloat
        global GTempInMinFloat
        global GPressMaxInt
        global GPressMinInt
        global GStartDay
        global GStartHour
        global GWindSpeedInt
        global GWindGustInt
        global GWindDirInt
        global GDayNight
        global GBattVoltageFloat
        global GTimeCheckLast
        SignalLevel = 0

#                 t=Night mode                                      Wind (Av)
#                 T=Day Mode                                        | | Wind (Gust)
#                 |  Out T   Hum.  Pressure  Rain (Day) Rain (Hr)   | | | | Wind Dir
#                 | |     |   | |   |     |   |       |   |     |   | | | | |   |
# Message Format: | 9 9 . 9 H 9 9 P 9 9 9 9 R 9 9 9 . 9 r 9 9 . 9 W 9 9 9 9 9 9 9
#                 ---------------------------------------------------------------
#                 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 2 2 2 2 2 2 2 2 2 2 3 3
#                 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1


        if (radio.available()):
                length = radio.getDynamicPayloadSize()
                receive_payload = radio.read(length)
                HumidInFloat, GTempInFloat = GetInsideTempHumid()
                GHumidInInt = int(HumidInFloat)
                HourCheck = int(datetime.datetime.now().hour)

                if (GTempInFloat > GTempInMaxFloat):
                        GTempInMaxFloat = GTempInFloat
                if (GTempInFloat < GTempInMinFloat):
                        GTempInMinFloat = GTempInFloat


                if (receive_payload.decode('utf-8')[0] == 'T'):
# Weather Data receive cycle
                        try:
                                GTempOutFloat = float(receive_payload.decode('utf-8')[1:5])
                                if (GTempOutFloat > GTempOutMaxFloat[0]):
                                        GTempOutMaxFloat[0] = GTempOutFloat
                                if (GTempOutFloat < GTempOutMinFloat[0]):
                                        GTempOutMinFloat[0] = GTempOutFloat
                        except:
                                GTempOutFloat = 0

                        try:
                                GHumidOutInt = int(receive_payload.decode('utf-8')[6:8])
                        except:
                                GHumidInt = 0

                        try:
                                GPressInt = int(receive_payload.decode('utf-8')[9:13])
                                if (GPressInt > GPressMaxInt):
                                        GPressMaxInt = GPressInt
                                if (GPressInt < GPressMinInt):
                                        GPressMinInt = GPressInt
                                GPressAvThisHour = (GPressLastInt + GPressInt)/2
                                GPressLastInt = GPressInt
                                SignalLevel += 1
                        except:
                                GPressInt = 0

                        try:
                                GRainFloat = float(receive_payload.decode('utf-8')[14:19])
                        except:
                                GRainFloat = 0

                        try:
                                GRainHFloat = float(receive_payload.decode('utf-8')[20:24])
                        except:
                                GRainHFloat = 0

                        try:
                                GWindSpeedInt = int(receive_payload.decode('utf-8')[25:27])
                        except:
                                GWindSpeedInt = 0

                        try:
                                GWindGustInt = int(receive_payload.decode('utf-8')[27:29])
                        except:
                                GWindGustInt = 0

                        try:
                                GWindDirInt = int(receive_payload.decode('utf-8')[29:32])
                        except:
                                GWindDirInt = 0

                        try:
                                TimeCheck = time.time()
                                if (TimeCheck - GTimeCheckLast) > 60:
                                        GTimeCheckLast=TimeCheck
                                        f=urllib.request.urlopen(BaseURL + "&field1=%s&field2=%s&field3=%s&field4=%s&field5=%s&field6=%s&field7=%s&field8=%s" % (GTempOutFloat, GHumidOutInt, GPressInt, GWindSpeedInt, GWindGustInt, GWindDirInt, GRainFloat, GRainHFloat))
                                        f.close()
                        except:
                                print("ThingSpeak Upload fail!")


                else :
# System status receive cycle
                        try:
                                GBattVoltageFloat=float(receive_payload.decode('utf-8')[1:6])
                        except:
                                GBattVoltageFloat = 0
                MainWindow.UpdateDisplay()
                GTimeoutStart = time.time()
                MainWindow.UpdateSignal(5)
        else:
                today = datetime.datetime.now()
                TimeNow = time.time()
                AckMessage=bytes(today.strftime('%s'),'utf-8')
                radio.writeAckPayload(1,AckMessage)
                if not (today.hour == GStartHour.hour):
                        GStartHour = today
                        GPressAvLastHour = GPressAvThisHour
                if not (today.day == GStartDay.day):
                        GTempOutMaxFloat = GTempOutMaxFloat[1:]+GTempOutMaxFloat[:1]
                        GTempOutMinFloat = GTempOutMinFloat[1:]+GTempOutMinFloat[:1]
                        GTempOutMaxFloat[0] = -99
                        GTempOutMinFloat[0] = 99
                        GTempInMaxFloat = -99
                        GTempInMinFloat = 99
                        GPressMaxInt = 0
                        GPressMinInt = 9999
                        GStartDay = today
                        MainWindow.UpdateTempHistory()
                        WriteINI()
                if (TimeNow - GTimeoutStart) > 25:
                        MainWindow.UpdateSignal(0)
        Window.after(10, Get_Weather_Updates)


#------------------------------------------------------------------------------------------------------
# Start Here
#------------------------------------------------------------------------------------------------------

# Global Variable

GTimeCheckLast=0
GStartDay = datetime.datetime.now()
GStartHour = GStartDay
GTimeoutStart = time.time()
GTempOutFloat = 0
GTempInFloat = 0
# We need to set the current Max/Min ([0]) to something we can guarantee will be correctly updated
# But the history max/min ([1:7]) can start with something that is displayable on the chart
# Note that the chart gets history values from Config.ini so should never display these start values
GTempOutMaxFloat = [-99,1,1,1,1,1,1]
GTempOutMinFloat = [99,-1,-1,-1,-1,-1,-1]
GITempOutMaxFloat = [-99,1,1,1,1,1,1]
GITempOutMinFloat = [99,-1,-1,-1,-1,-1,-1]
GTempInMaxFloat = -99
GTempInMinFloat = 99
GITempInMaxFloat = -99
GITempInMinFloat = 99
GHumidOutInt = 0
GHumidInInt = 0
GPressInt = 0
GPressMaxInt = 0
GPressMinInt = 9999
GPressLastInt = 0
GPressAvLastHour = 0
GPressAvThisHour = 0
GRainFloat = 0
GRainHFloat = 0
GWindSpeedInt = 0
GWindGustInt = 0
GWindDirInt = 0
#GDayNight = True							# True = Day, False = Night
GBattVoltageFloat = 0

# Initialize everything

DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4
radio = RF24(22, 0);							# Instantiate Radio with CE on GPIO22
Window = tk.Tk()							# Instantiate Tkinter GUI
Window.title("Weather Station")
Window.attributes("-fullscreen", True)
Window.configure(bg="#2561A0")						# A nice blue background
MainWindow = Display(Window)						# Instantiate the main GUI WIndow

ReadPipe = 0x544d52687c							# RF Read pipe address - same as Arduino sender

radio.begin()
radio.setAutoAck(True)
radio.enableAckPayload()
radio.enableDynamicPayloads()
radio.setPALevel(RF24_PA_HIGH)
radio.setDataRate(RF24_250KBPS)
radio.openReadingPipe(1,ReadPipe)
radio.startListening()

#Re-direct STDERR to log file
sys.stderr = open('Errorlog.txt','w')

# ThingSpeak
BaseURL = 'https://api.thingspeak.com/update?api_key=%s' %MyAPI

# Get INI file data and display
ReadINI()
MainWindow.UpdateTempHistory()

# Begin Loop

Window.after_idle(Get_Weather_Updates)
Window.mainloop()
