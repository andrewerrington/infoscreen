# infoscreen
New infoscreen code for 3D printed panel-mount Pi

I made a mini-rack with these 3D-printed modules:
https://www.thingiverse.com/thing:3022136

I found the supplied code and wiring to be a little cumbersome, so I modified them. Now all wires come to an
8-way header that can be plugged into the Pi GPIO, and routed through a small piece of perfboard to the display,
pushbutton, and LED. The slide switch is not in use.

The main modification was to allow the pushbutton to shut down the Pi cleanly, using the gpio-shutdown dtoverlay,
instead of via a menu option on the display. In addition, the button can be used to restart the Pi after is has
shut down.
