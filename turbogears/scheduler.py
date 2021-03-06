"""Module that provides a cron-like task scheduler.

This task scheduler is designed to be used from inside your own program.
You can schedule Python functions to be called at specific intervals or
days. It uses the standard 'sched' module for the actual task scheduling,
but provides much more:
    - repeated tasks (at intervals, or on specific days)
    - error handling (exceptions in tasks don't kill the scheduler)
    - optional to run scheduler in its own thread or separate process
    - optional to run a task in its own thread or separate process

If the threading module is available, you can use the various Threaded
variants of the scheduler and associated tasks. If threading is not
available, you could still use the forked variants. If fork is also
not available, all processing is done in a single process, sequentially.

There are three Scheduler classes:
    Scheduler    ThreadedScheduler    ForkedScheduler

You usually add new tasks to a scheduler using the add_interval_task or
add_daytime_task methods, with the appropriate processmethod argument
to select sequential, threaded or forked processing. NOTE: it is impossible
to add new tasks to a ForkedScheduler, after the scheduler has been started!
For more control you could use one of the following Task classes
and use schedule_task or schedule_task_abs:
    IntervalTask    ThreadedIntervalTask    ForkedIntervalTask
    WeekdayTask     ThreadedWeekdayTask     ForkedWeekdayTask
    MonthdayTask    ThreadedMonthdayTask    ForkedMonthdayTask

Kronos is the Greek God of Time.

This module is based on Kronos by Irmen de Jong, but has been modified
to better fit within TurboGears. Additionally, this module appeared to
no longer be supported/in development.
"""
#
#   $Id: kronos.py,v 1.5 2004/10/06 22:43:49 irmen Exp $
#
#   (c) Irmen de Jong.
#   This is open-source software, released under the MIT Software License:
#   http://www.opensource.org/licenses/mit-license.php
#


import os, sys
import sched, time
import traceback
import weakref

from turbogears.util import Enum

method = Enum("sequential", "forked", "threaded")

class Scheduler:
    """The Scheduler itself."""

    def __init__(self):
        self.running = True
        self.sched = sched.scheduler(time.time, self.__delayfunc)

    def __delayfunc(self, delay):
        # This delay function is basically a time.sleep() that is
        # divided up, so that we can check the self.running flag while delaying.
        # there is an additional check in here to ensure that the top item of
        # the queue hasn't changed
        if delay < 10:
            time.sleep(delay)
        else:
            toptime = self.sched.queue[0][0]
            endtime = time.time() + delay
            period = 5
            stoptime = endtime - period
            while self.running and stoptime > time.time() and \
                self.sched.queue[0][0] == toptime:
                time.sleep(period)
            if not self.running or self.sched.queue[0][0] != toptime:
                return
            now = time.time()
            if endtime > now:
                time.sleep(endtime - now)

    def _acquire_lock(self):
        pass

    def _release_lock(self):
        pass

    def add_interval_task(self, action, taskname, initialdelay, interval, processmethod, args, kw):
        """Add a new Interval Task to the schedule. A very short initialdelay or one of
        zero cannot be honored, you will see a slight delay before the task is first
        executed. This is because the scheduler needs to pick it up in its loop."""
        if initialdelay < 0 or interval < 1:
            raise ValueError("delay or interval must be >0")
        # Select the correct IntervalTask class. Not all types may be available!
        if processmethod == method.sequential:
            TaskClass=IntervalTask
        elif processmethod == method.threaded:
            TaskClass = ThreadedIntervalTask
        elif processmethod == method.forked:
            TaskClass = ForkedIntervalTask
        else:
            raise ValueError("invalid processmethod")
        if not args:
            args = []
        if not kw:
            kw = {}
        task = TaskClass(taskname, interval, action, args, kw)
        self.schedule_task(task, initialdelay)
        return task

    def add_daytime_task(self, action, taskname, weekdays, monthdays, timeonday, processmethod, args, kw):
        """Add a new Day Task (Weekday or Monthday) to the schedule."""
        if weekdays and monthdays:
            raise ValueError("you can only specify weekdays or monthdays, not both")
        if not args:
            args = []
        if not kw:
            kw = {}
        if weekdays:
            # Select the correct WeekdayTask class. Not all types may be available!
            if processmethod == method.sequential:
                TaskClass = WeekdayTask
            elif processmethod == method.threaded:
                TaskClass = ThreadedWeekdayTask
            elif processmethod == method.forked:
                TaskClass = ForkedWeekdayTask
            else:
                raise ValueError("invalid processmethod")
            task = TaskClass(taskname, weekdays, timeonday, action, args, kw)
        if monthdays:
            # Select the correct MonthdayTask class. Not all types may be available!
            if processmethod == method.sequential:
                TaskClass = MonthdayTask
            elif processmethod == method.threaded:
                TaskClass = ThreadedMonthdayTask
            elif processmethod == method.forked:
                TaskClass = ForkedMonthdayTask
            else:
                raise ValueError("invalid processmethod")
            task = TaskClass(taskname, monthdays, timeonday, action, args, kw)
        firsttime = task.get_schedule_time(True)
        self.schedule_task_abs(task, firsttime)
        return task

    def schedule_task(self, task, delay):
        """Low-level method to add a new task to the scheduler with the given delay (seconds)."""
        if self.running:
            self._acquire_lock() # lock the sched queue, if needed
            try:
                task.event = self.sched.enter(delay, 0, task,
                            (weakref.ref(self),) )
            finally:
                self._release_lock()
        else:
            task.event = self.sched.enter(delay, 0, task,
                        (weakref.ref(self),) )

    def schedule_task_abs(self, task, abstime):
        """Low-level method to add a new task to the scheduler for the given absolute time value."""
        if self.running:
            self._acquire_lock() # lock the sched queue, if needed
            try:
                task.event = self.sched.enterabs(abstime, 0, task,
                                    (weakref.ref(self),) )
            finally:
                self._release_lock()
        else:
            task.event = self.sched.enterabs(abstime, 0, task,
                                (weakref.ref(self),) )


    def start(self):
        """Start the scheduler."""
        self._run()

    def stop(self):
        """Remove all pending tasks and stop the Scheduler."""
        self.running = False
        self.sched.queue[:] = []

    def cancel(self, task):
        self.sched.cancel(task.event)

    def _run(self):
        # Low-level run method to do the actual scheduling loop.
        while self.running:
            try:
                self.sched.run()
            except Exception, e:
                print >> sys.stderr, "ERROR DURING SCHEDULER EXECUTION", e
                print >> sys.stderr, "".join(traceback.format_exception(*sys.exc_info()))
                print >> sys.stderr, "-"*20
            # queue is empty; sleep a short while before checking again
            if self.running:
                time.sleep(5)


class Task:
    """Abstract base class of all scheduler tasks"""
    def __init__(self, name, action, args, kw):
        """This is an abstract class!"""
        self.name = name
        self.action = action
        self.args = args
        self.kw = kw

    def __call__(self, schedulerref):
        """Execute the task action in the scheduler's thread."""
        try:
            self.execute()
        except Exception, e:
            self.handle_exception(e)
        self.reschedule(schedulerref())

    def reschedule(self, scheduler):
        """This is an abstract class, this method is defined in one of the sub classes!"""
        raise NotImplementedError("you're using the abstract base class 'Task', use a concrete class instead")

    def execute(self):
        """Execute the actual task."""
        self.action(*self.args, **self.kw)

    def handle_exception(self, exc):
        """Handle any exception that occured during task execution."""
        print >> sys.stderr, "ERROR DURING TASK EXECUTION", exc
        print >> sys.stderr, "".join(traceback.format_exception(*sys.exc_info()))
        print >> sys.stderr, "-"*20


class IntervalTask(Task):
    """A repeated task that occurs at certain intervals (in seconds)."""
    def __init__(self, name, interval, action, args=None, kw=None):
        Task.__init__(self, name, action, args, kw)
        self.interval = interval

    def reschedule(self, scheduler):
        # reschedule this task according to its interval (in seconds).
        if scheduler.running:
            scheduler.schedule_task(self, self.interval)



class DayTaskRescheduler:
    """A mixin class that contains the reschedule logic for the DayTasks."""
    def __init__(self, timeonday):
        self.timeonday = timeonday

    def get_schedule_time(self, today):
        """Calculate the time value at which this task is to be scheduled."""
        now = list(time.localtime())
        if today:
            # schedule for today. let's see if that is still possible
            if (now[3], now[4]) >= self.timeonday:
                now[2] += 1  # too bad, it will be tomorrow
        else:
            now[2] += 1   # tomorrow
        now[3], now[4] = self.timeonday     # set new time on day (hour,minute)
        now[5] = 0 # seconds
        return time.mktime(now)

    def reschedule(self, scheduler):
        # Reschedule this task according to the daytime for the task.
        # The task is scheduled for tomorrow, for the given daytime.
        # (The execute method in the concrete Task classes will check
        # if the current day is a day on which the task must run).
        if scheduler.running:
            abstime = self.get_schedule_time(False)
            scheduler.schedule_task_abs(self, abstime)


class WeekdayTask(DayTaskRescheduler, Task):
    """A task that is called at specific days in a week (1-7), at a fixed time on the day."""
    def __init__(self, name, weekdays, timeonday, action, args=None, kw=None):
        if type(timeonday) not in (list, tuple) or len(timeonday) != 2:
            raise TypeError("timeonday must be a 2-tuple (hour,minute)")
        if type(weekdays) not in (list, tuple):
            raise TypeError("weekdays must be a sequence of weekday numbers 1-7 (1 is Monday)")
        DayTaskRescheduler.__init__(self, timeonday)
        Task.__init__(self, name, action, args, kw)
        self.days = weekdays

    def execute(self):
        # This is called every day, at the correct time. We only need to
        # check if we should run this task today (this day of the week).
        weekday = time.localtime().tm_wday + 1
        if weekday in self.days:
            self.action(*self.args, **self.kw)

class MonthdayTask(DayTaskRescheduler, Task):
    """A task that is called at specific days in a month (1-31), at a fixed time on the day."""
    def __init__(self, name, monthdays, timeonday, action, args=None, kw=None):
        if type(timeonday) not in (list, tuple) or len(timeonday) != 2:
            raise TypeError("timeonday must be a 2-tuple (hour,minute)")
        if type(monthdays) not in (list, tuple):
            raise TypeError("monthdays must be a sequence of monthdays numbers 1-31")
        DayTaskRescheduler.__init__(self, timeonday)
        Task.__init__(self, name, action, args, kw)
        self.days = monthdays

    def execute(self):
        # This is called every day, at the correct time. We only need to
        # check if we should run this task today (this day of the month).
        if time.localtime().tm_mday in self.days:
            self.action(*self.args, **self.kw)


try:
    import threading

    class ThreadedScheduler(Scheduler):
        """A Scheduler that runs in its own thread."""
        def __init__(self):
            Scheduler.__init__(self)
            self._lock = threading.Lock()     # we require a lock around the task queue
        def start(self):
            # Start method that splices of a thread in which the scheduler will run.
            self.thread = threading.Thread(target=self._run)
            self.thread.setDaemon(True)
            self.thread.start()
        def stop(self):
            # Stop method that stops the scheduler and waits for the thread to finish.
            Scheduler.stop(self)
            try:
                self.thread.join()
            except AttributeError:
                pass
        def _acquire_lock(self):
            self._lock.acquire()    # lock the thread's task queue
        def _release_lock(self):
            self._lock.release()    # release the thread's task queue

    class ThreadedTaskMixin:
        """A mixin class to make a Task execute in a separate thread."""
        def __call__(self, schedulerref):
            # execute the task action in its own thread.
            threading.Thread(target=self.threadedcall).start()
            self.reschedule(schedulerref())
        def threadedcall(self):
            # This method is run within its own thread, so we have to
            # do the execute() call and exception handling here.
            try:
                self.execute()
            except Exception, e:
                self.handle_exception(e)

    class ThreadedIntervalTask(ThreadedTaskMixin, IntervalTask):
        """Interval Task that executes in its own thread."""
        pass
    class ThreadedWeekdayTask(ThreadedTaskMixin, WeekdayTask):
        """Weekday Task that executes in its own thread."""
        pass
    class ThreadedMonthdayTask(ThreadedTaskMixin, MonthdayTask):
        """Monthday Task that executes in its own thread."""
        pass

except ImportError:
    # threading is not available
    pass


if hasattr(os,"fork"):
    import signal

    class ForkedScheduler(Scheduler):
        """A Scheduler that runs in its own forked process."""
        def __del__(self):
            if hasattr(self, "childpid"):
                os.kill(self.childpid, signal.SIGKILL)
        def start(self):
            # Start method that forks of a new process in which the scheduler will run.
            pid = os.fork()
            if pid == 0:
                # we are the child
                signal.signal(signal.SIGUSR1, self.signalhandler)
                self._run()
                os._exit(0)
            else:
                # we are the parent
                self.childpid = pid
                del self.sched      # can no longer insert in the scheduler queue
        def stop(self):
            # Stop method that stops the scheduler and waits for the process to finish.
            os.kill(self.childpid, signal.SIGUSR1)
            os.waitpid(self.childpid, 0)
        def signalhandler(self, sig, stack):
            Scheduler.stop(self)

    class ForkedTaskMixin:
        """A mixin class to make a Task execute in a separate process."""
        def __call__(self, schedulerref):
            # execute the task action in its own process.
            pid = os.fork()
            if pid == 0:
                # we are the child
                try:
                    self.execute()
                except Exception, e:
                    self.handle_exception(e)
                os._exit(0)
            else:
                # we are the parent
                self.reschedule(schedulerref())

    class ForkedIntervalTask(ForkedTaskMixin, IntervalTask):
        """Interval Task that executes in its own process."""
        pass
    class ForkedWeekdayTask(ForkedTaskMixin, WeekdayTask):
        """Weekday Task that executes in its own process."""
        pass
    class ForkedMonthdayTask(ForkedTaskMixin, MonthdayTask):
        """Monthday Task that executes in its own process."""
        pass

_scheduler_instance = None

def _get_scheduler():
    global _scheduler_instance
    si = _scheduler_instance
    if not si:
        si = ThreadedScheduler()
        _scheduler_instance = si
    return si

def _start_scheduler():
    si = _get_scheduler()
    si.start()

def _stop_scheduler():
    if not _scheduler_instance:
        return
    si = _get_scheduler()
    si.stop()

def add_interval_task(action, interval, args=None, kw=None,
        initialdelay=0, processmethod=method.threaded, taskname=None):
    si = _get_scheduler()
    return si.add_interval_task(action=action, interval=interval, args=args,
            kw=kw, initialdelay=initialdelay,
            processmethod=processmethod, taskname=taskname)

def add_weekday_task(action, weekdays, timeonday, args=None, kw=None,
        processmethod=method.threaded, taskname=None):
    si = _get_scheduler()
    return si.add_daytime_task(action=action, taskname=taskname,
            weekdays=weekdays, monthdays=None, timeonday=timeonday,
            processmethod=processmethod, args=args, kw=kw)


def add_monthday_task(action, monthdays, timeonday,
        args=None, kw=None,
        processmethod=method.threaded, taskname=None):
    si = _get_scheduler()
    return si.add_daytime_task(action=action, taskname=taskname,
            weekdays=None, monthdays=monthdays, timeonday=timeonday,
            processmethod=processmethod, args=args, kw=kw)

def cancel(task):
    si = _get_scheduler()
    si.cancel(task)
