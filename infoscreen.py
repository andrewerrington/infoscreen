# Infoscreen driver using gpiod - low CPU usage, Pi 5 compatible

# Drive 128x64 OLED display on I2C
# Drive an LED on GPIO 22
# Monitor a button on GPIO 27 to wake display and change modes
# Button is also attached to GPIO 17 for gpio_shutdown overlay
# and attached to GPIO 3 to restart Pi after shutdown.

# In /boot/firmware/config.txt:
# dtoverlay=gpio-shutdown,gpio_pin=17,debounce=3000

# Also, enable i2c with raspi-config

# Check or install the following packages. If necessary, set up a venv:
# sudo apt-get install python3-luma.oled
# sudo apt-get install python3-pil
# sudo apt-get install python3-smbus2
# sudo apt-get install i2c-tools
# sudo apt-get install python3-psutil
# This package is not yet in Debian, so a venv is needed:
# sudo apt-get install python3-gpiod

# Check i2c display is detected at address 0x3c:
# sudo i2cdetect -y 1

# Run this script (infoscreen.py). Run in a venv if necessary.

# venv installation instructions:
# 1) Create a venv for infoscreen. Ensure it has access to already installed
# system packages
# e.g. if infoscreen.py is in a directory /home/pi/infoscreen
#
# cd /home/pi/infoscreen
#
# Now create the venv (called infoscreen)
#
# python3 -m venv --system-site-packages infoscreen
#
# 2) Install gpiod in the venv just created
#
# infoscreen/bin/pip3 install gpiod
#
# 3) Now we run infoscreen.py in the venv:
#
# infoscreen/bin/python infoscreen.py
#
#
# Choose a method to run at boot time.
# e.g. /etc/rc.local
#
# /etc/rc.local is no longer present in later Raspberry Pi OS, so
# it must be created.
#
# sudo nano /etc/rc.local
#
# Add the following lines:

# #!/bin/sh -e
#
# /home/pi/infoscreen/infoscreen/bin/python /home/pi/infoscreen/infoscreen.py &
#
# exit 0

# Now check/change permissions:
#
# sudo chown root:root /etc/rc.local
#
# sudo chmod 755 /etc/rc.local
#


from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

import gpiod
from gpiod.line import Direction, Value
from gpiod.line import Bias, Edge

import select
import os
import threading

from PIL import ImageFont

from datetime import datetime
from datetime import timedelta

import time
import subprocess
import psutil

# Raspberry Pi pin configuration:
chip_path = "/dev/gpiochip0"
BTN_PIN = 27
LED_PIN = 22
LED_state = False

# Timer for Display timeout (in seconds)
disp_timer = 0
DISP_TIMEOUT = 15

# Menu Variables
menu_state = 0 # 0 = Info; 1 = Page 1; 2 = Page 2

# Create the SSD1306 OLED object.
serial = i2c(port = 1, address = 0x3c)
disp = ssd1306(serial, width = 128, height = 32, rotate = 2)

# Set up font
iFont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)
#iFont = ImageFont.load_default()

def edge_type_str(event):
  if event.event_type is event.Type.RISING_EDGE:
    return "Rising"
  if event.event_type is event.Type.FALLING_EDGE:
    return "Falling"
  return "Unknown"

def async_watch_line_value(chip_path, line_offset, done_fd):
  with gpiod.request_lines(chip_path, consumer = "async-watch-line-value",
    config = {line_offset: gpiod.LineSettings(edge_detection = Edge.BOTH,
    bias = Bias.PULL_UP, debounce_period = timedelta(milliseconds = 12), )},
  ) as request:
    poll = select.poll()
    poll.register(request.fd, select.POLLIN)
    poll.register(done_fd, select.POLLIN)
    while True:
      for fd, _event in poll.poll():
        if fd == done_fd:
          # Cleanup here before exiting
          return
        # Handle edge events
        for event in request.read_edge_events():
          #print("offset: {}  type: {:<7}  event #{}".format(event.line_offset, edge_type_str(event), event.line_seqno))
          if event.line_offset == BTN_PIN and event.event_type is event.Type.FALLING_EDGE:
            btn_press()

# Set LED state
def set_line_value(chip_path, line_offset, value):
  with gpiod.request_lines(chip_path, consumer = "set_line_value",
    config = {line_offset: gpiod.LineSettings(direction = Direction.OUTPUT)},
  ) as request:
    request.set_value(line_offset, Value.ACTIVE if value else Value.INACTIVE)


# Return button state
def get_line_value(chip_path, line_offset):
  with gpiod.request_lines(chip_path, consumer = "get_line_value",
    config={line_offset: gpiod.LineSettings(direction = Direction.INPUT)},
  ) as request:
    return request.get_value(line_offset)

# Handle button press to change modes
def btn_press():
  global disp_timer
  global menu_state
  if time.time()-disp_timer >= DISP_TIMEOUT:
    menu_state = 0
  else:
    menu_state += 1
    if menu_state == 3:
      menu_state = 0
  disp_timer = time.time()

# Clear display and show startup message
disp.clear()
with canvas(disp) as draw:
  draw.rectangle(disp.bounding_box, outline = "white", fill = "black")
  draw.text((11,9),"Infoscreen Started", font = iFont, fill = "white")

time.sleep(3)
disp.clear()

last_second = -1

# Run the async executor (select.poll) in a thread to demonstrate graceful exit
done_fd = os.eventfd(0)

def bg_thread():
  try:
    async_watch_line_value(chip_path, BTN_PIN, done_fd)
  except OSError as ex:
    print(ex)
  print("Background thread exiting")

t = threading.Thread(target = bg_thread)
t.start()

# Main loop
while True:

  # This loops sleeps for 0.2s every time

  # Toggle LED state every second
  if LED_state != int(time.time()) % 2:
    LED_state = not LED_state
    set_line_value(chip_path, LED_PIN, LED_state)

  # Button pin is checked in the background by a thread

  this_second = int(time.time() - disp_timer)

  if this_second != last_second:
    last_second = this_second

    # If the display is active, and we are on a 1s boundary, update the display
    if time.time() - disp_timer < DISP_TIMEOUT:

      try:
        disp.show()
      except:
        pass

      if menu_state == 0:
        # Screen 0 shows Hostname, IP address, CPU % and MEM %
        # Shell scripts for system monitoring from here : https://unix.stackexchange.com/questions/119126/command-to-display-memory-usage-disk-usage-and-cpu-load
        cmd = "hostname"
        HOSTNAME =  subprocess.check_output(cmd, shell = True)
        cmd = "hostname -I | cut -d\' \' -f1"
        IP = subprocess.check_output(cmd, shell = True)

        # Examples of getting system information from psutil : https://www.thepythoncode.com/article/get-hardware-system-information-python#CPU_info
        CPU = "{:3.0f}".format(psutil.cpu_percent())
        svmem = psutil.virtual_memory()
        MemUsage = "{:2.0f}".format(svmem.percent)

        try:
          with canvas(disp) as draw:
            draw.text((0, 0),  "NAME: " + HOSTNAME.decode('UTF-8'), font = iFont, fill = "white")
            draw.text((0, 11), "IP  : " + IP.decode('UTF-8'), font = iFont, fill = "white")
            draw.text((0, 22), "CPU : " + CPU + "% | MEM: " + MemUsage + "%", font = iFont, fill = "white")
        except:
          pass

      if menu_state == 1:
        # Screen 1 shows uptime, load average, CPU temp
        uptime = ("%s"%(datetime.now()-datetime.fromtimestamp(psutil.boot_time()))).split(".")[0]
        load_avg = ["%.2f"%x for x in psutil.getloadavg()]
        cpu_T = float(subprocess.getoutput("vcgencmd measure_temp").split("=")[1].split("'")[0])
        try:
          with canvas(disp) as draw:
            draw.text((0, 0),  "UP  : %s"%uptime, font = iFont, fill = "white")
            draw.text((0, 11), "LOAD: %s"%",".join(load_avg), font = iFont, fill = "white")
            draw.text((0, 22), "TEMP: %s °C"%cpu_T, font = iFont, fill = "white")
        except:
          pass

      if menu_state == 2:
        # Screen 2 shows ???

        try:
          with canvas(disp) as draw:
            draw.text((0, 0),  ".......Menu 2.......", font = iFont, fill = "white")
            draw.text((0, 11), "012345678901234567890123", font = iFont, fill = "white")
            draw.text((0, 22), "--No info specified--", font = iFont, fill = "white")
        except:
          pass

    else:
      try:
        disp.clear()
        disp.hide()
      except:
        pass

  time.sleep(0.2)

GPIO.cleanup()
