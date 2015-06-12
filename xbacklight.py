#!/usr/bin/env python3

from __future__ import division, print_function

try:
  import xcffib
  from xcffib import xproto, randr
except ImportError:
  import xcb as xcffib
  from xcb import xproto, randr

import re, sys, time


class Backlight:
  def __init__(self, con=None, ext=None):
    """
        con: Optional existing xcb connection or display string.
        ext: RandR extension object associated with con.
    """
    if con is None or isinstance(con, str):
      self.con = con = xcffib.connect(display=con)
    if ext is None:
      self.ext = con(randr.key)
    # BackLight Atoms
    bla = [con.core.InternAtom(True, len(a), a.encode('latin-1')).reply().atom
        for a in ('Backlight', 'BACKLIGHT')]
    self.bla = [a for a in bla if a]
    if not bla:
      raise IOError("No outputs have backlight property")
    a = 'INTEGER'
    self.intatom = con.core.InternAtom(
        False, len(a), a.encode('latin-1')).reply().atom

  def get(self, outputs=None):
    """
        outputs: list of (scr_root, output_id) pairs, where None for either
            value will match anything.

        return: dict of {(scr_root, output_id): (bmin, cur, bmax)}, where
            the value tuples are the minimum, current, and maximum brightness
            values.
    """
    ret = {}
    setup = getattr(self.con, 'setup', None)
    if setup is None:
      setup = self.con.get_setup()
    screenSet, outputSet, totalSet = set(), set(), set()
    for pair in outputs or ():
      scr, output = pair
      if output is None:
        screenSet.add(scr)
      elif scr is None:
        outputSet.add(output)
      else:
        totalSet.add(pair)
    for scr in setup.roots:
      scr = scr.root
      res = self.ext.GetScreenResources(scr).reply()
      for output in res.outputs:
        if outputs and (scr, output) not in totalSet and \
            scr not in screenSet and output not in outputSet:
          continue
        for a in self.bla:
          r = self.ext.GetOutputProperty(output, a, 0, 0, 4, 0, 0).reply()
          if r.type != self.intatom or r.num_items != 1 or r.format != 32:
            continue
          cur = r.data[0]
          self.bla = (a,)
          break
        if cur is None:
          continue
        try:
          r = self.ext.QueryOutputProperty(output, a).reply()
        except Exception:
          continue
        if not r.range or r.length != 2:
          continue
        bmin, bmax = r.validValues
        ret[(scr, output)] = (bmin, cur, bmax)
    return ret

  def set(self, val, rel=False, percent=True, outputs=None, fps=30, dur=.2):
    """
        val: New brightness value.
        rel: Whether val is relative to (should be added to) current value.
        percent: Whether val is a percentage or native units.
        outputs: a dict of the form returned by Backlight.get().
        fps: Number of steps per second.
        dur: Number of seconds to complete the change.

        return: dict of form {(scr_root, output_id): new}, where new is
            resulting brightness level in native units.
    """
    if not hasattr(outputs, 'keys'):
      outputs = self.get(outputs)
    startt = time.time()
    target = {}
    rel = rel and 1 or 0
    for (k, (bmin, cur, bmax)) in outputs.items():
      if percent:
        new = (bmax - bmin) * (val + bmin) / 100 + rel * cur
      else:
        new = val + rel * cur
      new = int(round(new))
      if new <= bmin and (val != 0 or rel):
        new = bmin + 1
      target[k] = int(round(new))
    # XXX probably would be good to adjust fps automatically if abs(new - cur)
    # is less than steps.
    steps = fps * dur
    if steps < 1:
      steps = 1
    i = 1
    while i <= steps:
      done = (i == steps)
      for (k, (bmin, cur, bmax)) in outputs.items():
        scr, output = k
        new = target[k]
        v = int(round((new - cur) * i / steps + cur))
        self.ext.ChangeOutputProperty(output, self.bla[0], self.intatom, 32,
            xproto.PropMode.Replace, 1, [v])
      self.con.flush()
      if done:
        break
      time.sleep(1 / fps)
      i = round((time.time() - startt) * fps)
      if i > steps:
        i = steps
    return target


def main(display=None, arg='', verbose=False, outputs=(), **kws):
  bl = Backlight(display)
  old = bl.get(outputs)
  rel = arg.startswith('-') or arg.startswith('+')
  if arg.startswith('='):
    arg = arg[1:]
  percent = True
  if arg.endswith('%'):
    arg = arg[:-1]
  elif arg.endswith('='):
    percent = False
    arg = arg[:-1]
  if arg:
    new = bl.set(float(arg), outputs=old, rel=rel, percent=percent, **kws)
  if verbose:
    for (k, (bmin, cur, bmax)) in old.items():
      scr, output = k
      print('[{}:{}] {}, {}, {} ({:.2f}%)'.format(scr, output, bmin,
          cur, bmax, (cur - bmin) * 100 / (bmax - bmin)), end='')
      if arg:
        n = new[k]
        print(' => {} ({:.2f}%)'.format(n, (n - bmin) * 100 / (bmax - bmin)))
      else:
        print()
  elif not arg:
    vs = [(cur - bmin) * 100 / (bmax - bmin) for (bmin, cur, bmax) in
        old.values()]
    print('{:.6f}'.format(sum(vs) / len(vs)))


def intpair(s, sep=':'):
  if ':' not in s:
    return (int(s), None)
  a,b = s.split(sep, 1)
  if not b:
    return (int(a), None)
  if not a:
    return (None, int(b))
  return (int(a), int(b))

numberLikePat = re.compile(r'^([-+=])?([0-9.]+)[%=]?$')
def numberLike(s, abort=True, allowPrefix=True):
  m = numberLikePat.match(s)
  if not m or (not allowPrefix and m.group(1)):
    if abort:
      raise ValueError("not number-like: " + str(s))
    return False
  try:
    float(m.group(2))
  except ValueError:
    if abort:
      raise
    return False
  return s

def millisecs(s):
  if s.endswith('s'):
    s = s[:-1]
    return float(s) * 1000
  return float(s)


def parseargs():
  import argparse
  p = argparse.ArgumentParser(description="Uses the X11 RandR extension to "
      "get or set brightness level of displays.")
  p.add_argument('-d', '-display', '--display',
      help="Connect to specified display")
  p.add_argument('-v', '--verbose', action="store_true",
      help="Output more information")
  p.add_argument('-o', '--output', action="append", type=intpair,
      metavar="SCREEN_ROOT:OUTPUT", help="Only apply to specified outputs")
  p.add_argument('-version', '--version', action="store_true",
      help="Display version number and exit")
  g = p.add_mutually_exclusive_group()
  g.add_argument('-get', '--get', action="store_true", help="Get brightness")
  noPrefix = lambda s:numberLike(s, True, False)
  g.add_argument('-set', '--set', type=noPrefix, metavar="BRIGHTNESS",
      help="Set brightness")
  g.add_argument('-inc', '--increase', type=noPrefix, metavar="BRIGHTNESS",
      help="Increase brightness relative to current setting")
  g.add_argument('-dec', '--decrease', type=noPrefix, metavar="BRIGHTNESS",
      help="Decrease brightness relative to current setting")
  g.add_argument('arg', nargs='?', metavar="BRIGHTNESS",
      help="Change brightness. Prefix with =/-/+ to set/decrement/increment "
      "(default: set); Suffix with %%/= to specify number as "
      "percentage/native units (default: percentage).")
  p.add_argument('-t', '-time', '--time', type=millisecs, default=200,
      metavar="MILLISECONDS", help="Fade time")
  g = p.add_mutually_exclusive_group()
  g.add_argument('-f', '--fps', type=float, default=30,
      help="Frames per second")
  g.add_argument('-steps', '--steps', type=int,
      metavar="CARDINAL", help="Total number of steps to fade")
  (ns, rest) = p.parse_known_args()
  if rest:
    if len(rest) > 1 or not numberLike(rest[0], False) or ns.arg or \
        ns.set or ns.increase or ns.decrease:
      p.error("Unknown arguments: " + ', '.join(rest))
    ns.arg = rest[0]
  if ns.version:
    print("xbacklight.py version 1.0")
    sys.exit(0)
  kws = {'display':ns.display, 'dur':ns.time/1000, 'verbose':ns.verbose,
      'outputs':ns.output}
  if ns.steps:
    kws['fps'] = ns.steps / kws['dur']
  else:
    kws['fps'] = ns.fps
  if ns.set:
    kws['arg'] = ns.set
  elif ns.increase:
    kws['arg'] = '+' + ns.increase
  elif ns.decrease:
    kws['arg'] = '-' + ns.decrease
  elif ns.arg:
    kws['arg'] = ns.arg
  else:
    kws['arg'] = ''
  main(**kws)


if __name__ == '__main__':
  parseargs()
