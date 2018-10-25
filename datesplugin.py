# -*- coding: utf-8 -*-
"""
Plugin that searches for and displays dates
"""

import re
import logging
import time

from urllib import request
from urllib.error import HTTPError, URLError

from datetime import datetime, timedelta
from dateutil.rrule import rruleset, rrulestr
from dateutil.parser import parse
from icalendar import Calendar
from icalendar.prop import vDDDTypes, vDDDLists
from pytz import utc, timezone

from plugin import Plugin

DATES_LOG = logging.getLogger('HelpPluginLog')



class DatesPlugin(Plugin):
    """Collects help messages
    from all other plugins and displays them"""
    def __init__(self, name, bot):
        DATES_LOG.debug("Creating DatesPlugin")
        Plugin.__init__(self, name, bot)
        DATES_LOG.debug("Adding matcher for '!dates'")
        Plugin.add_matcher(self, re.compile("![Dd]ates"))

        self.bot = bot #safe for later use
        self.help_text = ""
        self.first_run = True
        DATES_LOG.debug("scheduling job at 1min")
        bot.schedule.every(1).minutes.do(self.test)
        bot.schedule.every(5).minutes.do(self.dates_announce_next_talks)

    def test(self):
        DATES_LOG.debug("Dates test called by scheduler")
        self.bot.send("1min gone; could have done something useful here")

    def callback(self, room, event):
        """send collected help messages"""
        DATES_LOG.debug("%s sends response", self.name)
        self.dates(room)
        #room.send_text(self.collect_help())

    def get_help(self):
        """Return help text"""
        return "Prints Bytespeicher calendar entries at !dates"

    def dates(self, room):
        """Show the planned dates within the next days
            %%dates
        """

        now = datetime.utcnow().replace(hour=0,
                                        minute=0,
                                        second=0,
                                        microsecond=0)

        self._update_cache(room)

        self.output_dates(now,
                          now + timedelta(days=21),
                          'Bytespeicher',
                          room)


        # def cccongress_update_cron(self):
        #    """Update ical file"""
        #   
        #    yield from _update_cache(bot)
    
    
    def dates_announce_next_talks(self):
        """Announce next dates"""
        now = datetime.utcnow().replace(second=0,
                                        microsecond=0)
        for minutes in [10, 1440]:
            self.output_dates(now + timedelta(minutes=int(minutes-10)),
                              now + timedelta(minutes=int(minutes)),
                              'Bytespeicher',
                              self.all_rooms,
                              int(minutes))
    

    def output_dates(self, now, then, filter_location, room, announce=0):
        """
        Output dates between now and then and filter default location.
        Set announce greater 0 to add announce message and
        suppresses the No dates found message.
        """

        try:
            file = open('tmp/dates.cache')
            raw_text = file.read()
        except OSError as e:
            raise Exception(e)

        try:
            cal = Calendar.from_ical(raw_text)
            found = 0

            data = []
            timezone_ef = timezone('Europe/Berlin')
            fmt = "%d.%m.%Y %H:%M"

            # iterate all VEVENTS
            for event in cal.walk('VEVENT'):
                start = vDDDTypes.from_ical(event["DTSTART"])

            # check if DTSTART could be casted into some instance of
            # dateime. If so, this indicates an event with a given start
            # and stop time. There are other events too, e.g. Events
            # lasting a whole day. Reading DTSTART of such whole day
            # events will result in some instance of date. We will
            # handle this case later.

                if isinstance(start, datetime):
                    rset = rruleset()  # create a set of recurrence rules
                    info = ""
                    loc = ""

                    # Everyone interested in calendar events wants to get
                    # some summary about the event. So each event
                    # handled here has to have a SUMMARY. If not, we will
                    # discard handling the VEVENT here
                    if "SUMMARY" in event:
                        info = event["SUMMARY"]
                    else:
                        continue  # events ohne summary zeigen wir nicht an!

                    # Printing the location of an event is important too.
                    # However,
                    # the string containing location info may be too long
                    # to be viewed nicely in IRC.
                    # We filter our default location and strip every other
                    # location to the location name without address.

                    if "LOCATION" in event:
                        if not event["LOCATION"].startswith(filter_location):
                            loc = event["LOCATION"].split(', ')[0]

                    # Recurrence handling starts here.
                    # First, we check if there is a recurrence rule (RRULE)
                    # inside the VEVENT, If so, we use the ical like
                    # expression of DTSTART and RRULE to feed
                    # our ruleset with.
                    if "RRULE" in event:  # recurrence
                        ical_dtstart = (event.get("DTSTART")).to_ical().decode()
                        ical_rrule = (event.get('RRULE')).to_ical().decode()
                        rset.rrule(rrulestr(ical_rrule,
                                            dtstart=parse(ical_dtstart),
                                            ignoretz=1))

                        # Recurrence handling includes exceptions in EXDATE.
                        # First we check if there are EXDATE values. If there
                        # is only one we will convert this also to a list to
                        # simplify handling. We use list entries to feed our
                        # ruleset with.
                        if "EXDATE" in event:
                            ical_exdate = event.get('EXDATE')
                            if isinstance(ical_exdate, vDDDLists):
                                ical_exdate = [ical_exdate]
                            for exdate in ical_exdate:
                                rset.exdate(parse(exdate.to_ical()))

                        # the ruleset now may be used to calculate any datetime
                        # the event happened and will happen.
                        # Since we are only interested
                        # in upcoming events between now and then, we just use
                        # the between() method of the ruleset which will return an
                        # array of datetimes. Since timeutils cares about tumezones,
                        # no convertion between utc and ME(S)Z needs to be done.
                        # We just iterate the array of datetimes and put starting
                        # time (DTSTART) info (SUMMARY) and location (LOCATION)
                        # into our "database" of events
                        for e in rset.between(now, then):
                            found += 1
                            data.append({
                                'datetime': e.strftime(fmt),
                                'datetime_sort': e.strftime(fmt),
                                'info': info,
                                'loc': loc,
                            })

                        # Recurrence rules do also know about EXDATEs, handling this
                        # should be easy through rset (ruleset)...
                        # TODO handling of EXDATE

                    else:  # no recurrence

                        # there was no recurrence rule (RRULE), so we do not need
                        # to handle recurrece for this VEVENT. We do, however, need
                        # to handle conversion between UTC and ME(S)Z, because now
                        # timeutils, which would do this for us automatically, is
                        # not involved
                        #
                        # first we check if the DTSTART is between now and then.
                        # If so, we put the VEVENTs starttime (DTSTART), info
                        # (SUMMARY) and location (LOCATION) into our database.

                        if start < utc.localize(now) or start > utc.localize(then):
                            continue

                        found += 1
                        data.append({
                            'datetime': start.astimezone(timezone_ef).strftime(fmt),
                            'datetime_sort':
                                start.astimezone(timezone_ef).strftime(fmt),
                            'info': info,
                            'loc': loc,
                        })

                # So far we only have handled short time events, but there are
                # whole day events too. So lets handle them here...
                #
                # TODO handling of whole day events
                #
                # if isinstance(start, date):

            # lets sort our database, nearest events coming first...
            data = sorted(data,
                          key=lambda k: time.mktime(datetime.strptime(
                              k['datetime_sort'], "%d.%m.%Y %H:%M").timetuple()))

            # Spit out all events in database into IRC. Suppress duplicate lines
            # from nonconforming ics files. Add message on announcing events. If
            # there were no events, print some message about this...

            if found > 0 and announce > 0:
                room.send_text("Please notice the next following event(s):")

            last_output = None
            for event in data:
                output = "  %s - %s" % (event['datetime'], event['info'])
                if event['loc']:
                    output = "%s (%s)" % (output, event['loc'])

                if last_output != output:
                    last_output = output
                    room.send_text(output)

            if found == 0 and announce == 0:
                room.send_text(
                    "No dates during the next %d days" % 21
                )

        except KeyError:
            room.send_text("Error while retrieving dates data")
            raise Exception()


    def _update_cache(self, room):
        """Update cached ical file"""
        url = 'http://www.google.com/calendar/ical/2eskb61g20prl65k2qd01uktis%40group.calendar.google.com/public/basic.ics'
        try:
            #Request the ical file.
            with request.urlopen(url) as resp:
                DATES_LOG.debug("URL requested")
                if resp.status == 200:
                    #Get text content from http request.
                    DATES_LOG.debug("Get text")
                    r_raw = resp.read()
                    encoding = resp.headers.get_content_charset('utf-8')
                    text = r_raw.decode(encoding)
                else:
                    room.send_text("Error while retrieving calendar data")
                    raise Exception()
        except HTTPError as e:
            DATES_LOG.error('HTTPError = %s', str(e.code))
            room.send_text("Error while retrieving calendar data\n"
                                'HTTPError = ' + str(e.code))
        except URLError as e:
            DATES_LOG.error('URLError = %s', str(e.reason))
            room.send_text("Error while retrieving calendar data\n"
                                'URLError = ' + str(e.reason))

        try:
            # Save ical cache to disk
            cache = open('tmp/dates.cache', "w")
            cache.truncate(0)
            cache.write('%s' % text)
            cache.close()

        except OSError as e:
            DATES_LOG.error(e)