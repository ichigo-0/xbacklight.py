# xbacklight.py
Python-based replacement for
[xbacklight](http://cgit.freedesktop.org/xorg/app/xbacklight/). It probably can
be used as a drop-in replacement. Like the original, it uses the X11 RandR
extension to get and set the display's backlight brightness. The main new
feature is the ability to make adjustments in units smaller than one percent,
e.g. `xbacklight.py +0.2` to increase brightness by 0.2%.

Requirements: [python](https://www.python.org/) (tested with 2.7 and 3.4), [xcffib](https://github.com/tych0/xcffib) (or [xpyb](https://pypi.python.org/pypi/xpyb/1.3.1)).
