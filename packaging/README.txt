LUOM What's New
===============

A free utility for members of Lumos Ultra Owners & Makers (LUOM):
https://www.facebook.com/groups/lumosultraownersmakers

It keeps track of the WeCreat help site (help.wecreat.com) and shows every
article that matters for the WeCreat Lumos Ultra, newest first. Each time
it checks the site, anything new or changed since the last check is
highlighted at the top of the list.

It runs on your own computer and opens in your web browser. It only reads
the public help site; nothing is sent anywhere.


WHAT THIS PROGRAM IS - AND IS NOT
---------------------------------

LUOM What's New is an indexer, searcher and cataloger. It reads WeCreat's
public knowledge base, lists the articles that concern the Lumos Ultra,
notes what is new or changed, and links you to each original article on
help.wecreat.com.

  - LUOM does NOT write, maintain, host or own WeCreat's knowledge base,
    and cannot correct, update or remove any article in it.
  - This program is NOT affiliated with, endorsed by or sponsored by
    WeCreat. It is not an official WeCreat product or support channel.
    For official help or warranty questions, contact WeCreat through
    help.wecreat.com.
  - The articles (text, titles, images, videos) belong to WeCreat. The
    program shows only titles and short excerpts, each linked to the
    original. Always read the full, current article on WeCreat's site.
  - The index it builds is for your personal use on your own computer.
    Please do not republish articles or share the index files.
  - WeCreat, Lumos Ultra and MakeIt are names and trademarks of their
    owner, used here only to describe what this program works with.

The program is free and provided as is, without any warranty.


WHAT'S IN THIS FOLDER
---------------------

  LUOM-WhatsNew.pyz              the program
  Start LUOM What's New.cmd      double-click this on Windows
  Start LUOM What's New.command  double-click this on a Mac
  start-luom-whatsnew.sh         run this on Linux
  LUOM-WhatsNew.ico              the LUOM icon, for a shortcut (see below)
  README.txt                     this file

If you used this program before under the name WhatsNewWecreat, your data
is moved to the new folder automatically the first time you start it.

Keep these files together in one folder. Any folder is fine, for example
Documents\LUOM What's New.


STARTING IT
-----------

Windows:  double-click "Start LUOM What's New".
Mac:      double-click "Start LUOM What's New.command". The first time,
          macOS may say it is from an unidentified developer: right-click
          the file, choose Open, then Open again.
Linux:    open a terminal in this folder and run  ./start-luom-whatsnew.sh

Your web browser opens the LUOM What's New page. The very first time, it
explains that there is no data yet and offers to download it - click
"Download index now". It takes a few seconds.

To check the help site again later, click "Run scan". The time of the
last check is shown next to the button.

To stop the program, click the power button at the top right of the page.
Closing the browser tab alone leaves it running in the background; opening
"Start LUOM What's New" again simply brings the page back.

The "LUOM on Facebook" button at the top of the page opens our group.

Two options sit under the search filters, and the page remembers them:

  - "Show articles not about the Lumos Ultra" - the program keeps a list
    of the whole WeCreat knowledge base, but normally shows only the
    Lumos Ultra articles. Tick this to see the rest too; each one says
    why it is not counted as a Lumos Ultra article.
  - "Open articles in" - a separate browser window beside the program
    (the default; the same window is reused for every article), the
    same browser tab each time, or a new tab each time.


A DESKTOP SHORTCUT WITH THE LUOM ICON (WINDOWS, OPTIONAL)
---------------------------------------------------------

1. Right-click "Start LUOM What's New" and choose Show more options >
   Send to > Desktop (create shortcut).
2. Right-click the new shortcut on the desktop, choose Properties, then
   Change Icon... > Browse..., and pick LUOM-WhatsNew.ico in this folder.
3. Optionally rename the shortcut to "LUOM What's New".
4. To start it without a black window flashing up, set Run: to Minimized
   in the same Properties window.


PYTHON
------

LUOM What's New needs Python 3.8 or newer, free from python.org. You do not
need to know anything about it.

If Python is missing, the start file tells you and offers to install it:

  Windows  installs Python 3.12 for your user account with winget, the
           package manager built into Windows 10 and 11. No administrator
           password is needed. If winget is not available, the python.org
           download page opens instead - install with the default options.
  Mac      uses Homebrew if you have it, otherwise opens the python.org
           download page.
  Linux    offers the install command for your distribution (it asks for
           your password).

Nothing is installed unless you say yes.


WHERE THE DATA IS KEPT
----------------------

  Windows  C:\ProgramData\LUOM-WhatsNew
  Mac      /Users/Shared/LUOM-WhatsNew
  Linux    ~/.local/share/luom-whatsnew

The data is shared by everyone who uses this computer. Deleting that
folder starts over from scratch; the program will offer a fresh download.

To change which articles are included, put a config.json file (the rules
file from the project) in that folder.

If something goes wrong on Windows, a log file named luom-whatsnew.log
is written to the same folder.


CHECKING AUTOMATICALLY (OPTIONAL)
---------------------------------

To check the help site on a schedule even when the page is not open:

Windows Task Scheduler - create a basic task, weekly, action "Start a
program":
    Program:    the full path to "Start LUOM What's New.cmd"
    Arguments:  scan

Mac / Linux cron, e.g. every Monday at 8:00:
    0 8 * * 1  /path/to/start-luom-whatsnew.sh scan

The page shows what the scheduled check found the next time you open it.
