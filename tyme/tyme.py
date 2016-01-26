from collections import OrderedDict, ChainMap
from datetime import datetime, timedelta
import itertools
import re
from tempfile import NamedTemporaryFile
from typing import Iterable
import os
import shutil
import subprocess

from fuzzyfinder import fuzzyfinder

TIME_FMT = '%m-%d %H:%M'
REGEX = {
    'total_time': r'(?: \(\d\d:\d\d\)  )',
    'task':       r'(?: (?: \w+[ ]?)+\w  )',
    'date':       r'(?: \d+-\d+[ ]\d\d:\d\d  )',
    'tags':       r'(?: [\w ,]+\w  )',
}

class TymeError(Exception): pass
class ParseError(TymeError): pass

class OrderedSet(OrderedDict):
    """An ordered set."""
    def __init__(self, elts):
        super().__init__((elt, None) for elt in elts)

    def add(self, elt):
        if elt in self:  # TODO necessary?
            raise ValueError('Element already in set.')
        self[elt] = None

        
class TymeSheet(object):
    """Master of tyme."""
    file = os.path.expanduser('~/.tyme/sheet')

    def __init__(self, todo=(), time=(), done=()) -> None:

        # figuring out ordered dict
        # what to do about classes? should from_file call methods to create task objects?
        self.todo = OrderedDict(todo)
        self.time = list(time)
        self.done = OrderedDict(done)

        if not os.path.isfile(self.file):
            path, base = os.path.split(self.file)
            os.makedirs(path, exist_ok=True)
            self.save(backup=False)

    @property
    def current_entry(self):
        if self.time and self.time[-1].end is None:
            return self.time[-1]
        else:
            return None

    def add_task(self, name, tags=(), deadline=None):
        if name in self.todo:
            raise TymeError('That task already exists.')
        task = Task(name, tags, deadline)
        self.todo[name] = task

    def clock_in(self, task, time=None):
        time = time or now()
        if self.current_entry:
            self.clock_out(time)
        entry = Entry(task, time, None)
        self.time.append(entry)

    def clock_out(self, time=None):
        if not self.current_entry:
            raise TymeError('Not clocked in.')
        task = self.current_entry.task
        self.current_entry.end = time or now()
        return task

    def complete_task(self, task_name, time=None):
        try:
            task = self.todo.pop(task_name)
        except KeyError:
            raise TymeError('No such task.')
        else:
            time = time or now()
            task.deadline = time
            self.done[task_name] = task
            if self.current_entry and self.current_entry.task == task_name:
                self.clock_out(time)

    def tag_filter(self, *tags) -> 'TymeSheet':
        if not tags:
            return self
        filter_tags = set(tags)

        todo = OrderedDict((n, t) for n, t  in self.todo.items() 
                           if filter_tags <= set(t.tags))
        done = OrderedDict((n, t) for n, t  in self.done.items() 
                           if filter_tags <= set(t.tags))
        all_tasks = ChainMap(todo, done)
        time = (e for e in self.time if e.task in all_tasks)
        return TymeSheet(todo, time, done)

    def edit(self) -> 'TymeSheet':
        """Edit the TymeSheet in an editor, returning a new modified timesheet."""
        with NamedTemporaryFile('w+') as tf:
            tf.write(str(self))
            tf.flush()
            editor = os.environ.get('EDITOR', 'vi')
            subprocess.call('{editor} {tf.name}'.format_map(locals()), shell=True)
            return TymeSheet.from_file(tf.name)

    def find_task(self, query):
        if isinstance(query, list):
            query = ' '.join(query)
        matches = fuzzyfinder(query, self.todo)
        try:
            return next(matches)
        except StopIteration:
            raise TymeError('No matching task found.')

    @classmethod
    def from_file(cls, file=None):
        """Creates a TymeSheet from a file in the standard format."""
        file = file or cls.file
        file = (line for line in open(file)
                if len(line) > 2)  # skip empty lines

        def assert_match(regex, line, fail_msg):
            m = re.match(regex, line)
            if not m:
                raise ParseError(fail_msg + ': ' + line)

        assert_match(r' {10,}Todo', next(file), 'No Todo')
        assert_match(r'-{10,}', next(file), 'No Todo line')

        def parse(line_class, file, break_word):
            break_re = re.compile(r' {10,}%s' % break_word)
            for line in file:
                if break_re.match(line):
                    assert_match(r'-{10,}', next(file), 'No line')
                    return
                yield line_class.from_string(line)

            if break_word is not None:
                # If we get here, we never found the next header.
                raise ParseError('Missing section: ' + break_word)

        todo = ((t.name, t) for t in parse(Task, file, 'Time'))
        time = parse(Entry, file, 'Done')
        done = ((t.name, t) for t in parse(Task, file, None))

        sheet = TymeSheet(todo, time, done)
        sheet._validate()
        return sheet

    def __str__(self):
        def section(title, lines):
            yield '{:^70}'.format(title)
            yield '-' * 70
            yield from lines
            yield ''

        return '\n'.join(itertools.chain(
            section('Todo', (t.to_string(self) for t in self.todo.values())),
            section('Time', (str(e) for e in self.time)),
            section('Done', (t.to_string(self) for t in self.done.values()))
        ))

    def to_file(self, file):
        string = str(self)  # make sure this works before overwriting file
        with open(file, 'w+') as f:
            f.write(string)

    def save(self, backup=True):
        if backup:
            shutil.copy(self.file, self.file + '~')
        self.to_file(self.file)

    def _validate(self):
        def check(bul, msg):
            if not bul:
                raise ParseError(msg)

        for t in self.time[:-1]:
            check(t.end is not None, 'Unfinished nonfinal entry')


class Task(object):
    """A task."""
    regex = re.compile(r'''
        {total_time}?  # optional total time
        \s*
        ({task})         # task
        (\s\s+{date})?        # optional deadline
        (\s\s+{tags})?        # optional tags
    '''.format_map(REGEX), re.VERBOSE)

    #test = '(00:50)  go to bed  10-10 07:15  foo, bar, wug '
    #print(regex.match(test).groups())
    
    def __init__(self, name: str, tags=(), deadline=None) -> None:
        self.name = name
        self.tags = tags
        self.deadline = deadline

    @classmethod
    def from_string(cls, string) -> 'Task':
        match = cls.regex.match(string)
        if not match:
            raise ParseError('Bad Task: ' + string)
        
        task, deadline, tags = match.groups()
        tags = tags.strip().split(', ') if tags else ()
        deadline = parse_time(deadline) if deadline else None
        return Task(task, tags, deadline)

    def to_string(self, sheet: TymeSheet) -> str:
        total = fmt_delta(self.time(sheet))
        name = '{:20}'.format(self.name)
        deadline = '{:11}'.format(fmt_time(self.deadline) if self.deadline else '')
        tags = ', '.join(self.tags)
        return '   '.join((total, name, deadline, tags)).strip()

    def entries(self, sheet: TymeSheet) -> 'Iterable[Entry]':
        return (e for e in sheet.time
                if e.task == self.name)

    def time(self, sheet: TymeSheet) -> timedelta:
        return sum((e.time for e in self.entries(sheet)), timedelta())

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name


class Entry(object):
    """docstring for Entry"""
    regex = re.compile(r'''
        (?:\(\d\d:\d\d\)\s)?      # optional total time
        \s*
        (\w[\w ]+\w)              # task
        \s+
        (\d+-\d+[ ]\d\d:\d\d)     # start
        \s+
        (--|\d+-\d+[ ]\d\d:\d\d)  # end
        ''', re.VERBOSE)

    regex = re.compile(r'''
        {total_time}?  # optional total time
        \s*
        ({task})         # task
        \s\s+
        ({date})        # start
        \s\s+
        (--|{date})        # end
    '''.format_map(REGEX), re.VERBOSE)


    def __init__(self, task: str, start: datetime, end: datetime) -> None:
        if end is not None and end < start:
            raise TymeError('Entry cannot end before it begins!')
        self.task = task
        self.start = start
        self.end = end

    @property
    def time(self):
        if self.end is None:
            return now() - self.start
        return self.end - self.start

    def __str__(self):
        end = '--' if self.end is None else fmt_time(self.end)
        return '   '.join((
            fmt_delta(self.time),
            '{:20}'.format(self.task),
            fmt_time(self.start),
            end
            ))

    @classmethod
    def from_string(cls, string):
        match = cls.regex.match(string)
        if not match:
            raise ParseError('Cannot parse entry:\n' + string)
        
        task, start, end = match.groups()
        start = parse_time(start)
        end = None if end == '--' else parse_time(end)
        return Entry(task, start, end)


def parse_time(string):
    string = string.strip()
    try:
        return datetime.strptime(string, TIME_FMT).replace(year=2000)
    except ValueError:
        now_ = now()
        return datetime.strptime(string, '%H:%M').replace(
                  year=2000, month=now_.month, day=now_.day)

def now():
    return datetime.now().replace(year=2000)

def fmt_delta(delta: timedelta):
    secs = delta.total_seconds()
    hrs = secs // 60 ** 2
    mins = secs // 60 % 60
    return '({:02.0f}:{:02.0f})'.format(hrs, mins)

def fmt_time(time: datetime):
    return time.strftime(TIME_FMT)

if __name__ == '__main__':
    sheet = TymeSheet.from_file('sheet.txt')
    print(Task.from_string('(00:50)  go to bed  10-10 07:15  foo, bar, wug ').to_string(sheet))

    Entry.from_string('(00:50)  go to bed  10-10 07:15   10-10 08:10   ')
    Task.from_string('(00:50)  write      foo, bar')
    Task.from_string('(01:50)  write      ')




    sheet.add_task('leave my house')
    sheet.complete_task('leave my house')
    sheet.clock_in('foo')
    sheet.clock_out()
    #sheet = sheet.tag_filter('personal', 'bed')
    sheet.to_file('sheet2.txt')
        
        
