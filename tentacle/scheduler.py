"""Model used to store events."""

import datetime

import celery.schedules
from celery.beat import Scheduler, ScheduleEntry

# Possible values for PeriodicTask.Interval.period
PERIODS = ('days', 'hours', 'minutes', 'seconds', 'microseconds')


class Interval(object):
    """Object used to model a periodic interval."""

    _every = None
    _period = None

    @property
    def every(self):
        return self._every

    @property.setter
    def every(self, value):
        if value is None:
            self._every = 0
            return

        try:
            val = int(value)
            if val < 0:
                raise ValueError()
        except Exception:
            raise ValueError("value must be an integer greater or equal to 0.")

    @property
    def period(self):
        if self._period is None:
            raise ValueError("'period' attribute cannot be None.")
        return self._period

    @property.setter
    def period(self, value):
        if value not in PERIODS:
            raise ValueError("value must be one of: 'days', 'hours', 'minutes', \
                             'seconds', 'microseconds'")
        else:
            self._period = value

    @property
    def schedule(self):
        """Return the object in the Celery schedule format."""
        return celery.schedules.schedule(
            datetime.timedelta(**{self.period: self.every})
        )

    @property
    def period_singular(self):
        """Show the period as a singular."""
        return self.period[:-1]

    def __unicode__(self):
        """Define a representation for the object."""
        if self.every == 1:
            return 'every {0.period_singular}'.format(self)
        return 'every {0.every} {0.period}'.format(self)

    def to_dict(self):
        """Serialize this object to a dict."""
        return {'every': self._every, 'period': self._period}

    @classmethod
    def from_dict(cls, data):
        """Deserialize from a dict."""
        result = cls()
        result._every = data['every']
        result._period = data['period']
        return result


class Crontab(object):
    """Object used to model a crontab."""

    minute = '*'
    hour = '*'
    day_of_week = '*'
    day_of_month = '*'
    month_of_year = '*'

    @property
    def schedule(self):
        """Return the object in the Celery schedule format."""
        return celery.schedules.crontab(minute=self.minute,
                                        hour=self.hour,
                                        day_of_week=self.day_of_week,
                                        day_of_month=self.day_of_month,
                                        month_of_year=self.month_of_year)

    def __unicode__(self):
        """Define a representation for the object."""
        return '{0} {1} {2} {3} {4} (m/h/d/dM/MY)'.format(
            self.minute, self.hour, self.day_of_week,
            self.day_of_month, self.month_of_year
        )

    def to_dict(self):
        """Serialize this object to a dict."""
        output = {}
        for key in ['minute', 'hour', 'day_of_week',
                    'day_of_month', 'month_of_year']:
            output.update({key: getattr(self, key)})

        return output

    @classmethod
    def from_dict(cls, data):
        """Deserialize from a dict."""
        result = cls()
        for key in ['minute', 'hour', 'day_of_week',
                    'day_of_month', 'month_of_year']:
            setattr(result, key, data.get(key, '*'))
        return result


class TaskModel(object):
    """Task model."""

    name = None
    task = None

    interval = Interval()
    crontab = Crontab()

    args = None
    kwargs = None

    queue = None
    exchange = None
    routing_key = None
    soft_time_limit = None

    expires = None
    enabled = None

    last_run_at = None

    total_run_count = None

    date_changed = None
    description = None

    run_immediately = False

    def validate(self):
        """Validation to ensure that you only have
        an interval or crontab schedule, but not both simultaneously."""
        if self.interval and self.crontab:
            msg = 'Cannot define both interval and crontab schedule.'
            raise ValueError(msg)
        if not (self.interval or self.crontab):
            msg = 'Must defined either interval or crontab schedule.'
            raise ValueError(msg)

    @property
    def schedule(self):
        if self.interval:
            return self.interval.schedule
        elif self.crontab:
            return self.crontab.schedule
        else:
            raise Exception("must define interval or crontab schedule")

    def __unicode__(self):
        fmt = '{0.name}: {{no schedule}}'
        if self.interval:
            fmt = '{0.name}: {0.interval}'
        elif self.crontab:
            fmt = '{0.name}: {0.crontab}'
        else:
            raise Exception("must define interval or crontab schedule")
        return fmt.format(self)


class EventEntry(ScheduleEntry):
    pass


class EventScheduler(Scheduler):
    pass
